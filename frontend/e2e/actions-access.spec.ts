import { readFileSync } from "node:fs";
import { expect, test, type Page } from "@playwright/test";

type Seed = {
  password: string;
  accounts: Record<string, string>;
  workspace_id: string;
  action_id: string;
  guest_phone: string;
};

const seed = (): Seed =>
  JSON.parse(readFileSync(process.env.E2E_SEED_PATH as string, "utf-8"));

const ACTIONS_LINK = 'a[href="/dashboard/actions"]';

async function login(page: Page, account: string) {
  const data = seed();
  await page.context().addCookies([
    { name: "NEXT_LOCALE", value: "en", url: "http://localhost:3100" },
  ]);
  await page.goto("/login");
  await page.locator("#email").fill(data.accounts[account]);
  await page.locator("#password").fill(data.password);
  await page.locator('form button[type="submit"]').click();
  await page.waitForURL(/\/dashboard/);
}

async function openActions(page: Page) {
  const listing = page.waitForResponse(
    (response) =>
      new URL(response.url()).pathname === "/api/v1/actions" &&
      response.request().method() === "GET",
  );
  await page.goto("/dashboard/actions");
  return listing;
}

for (const account of ["owner", "admin", "member_both"]) {
  test(`${account} reads and operates actions`, async ({ page }) => {
    await login(page, account);
    await expect(page.locator(ACTIONS_LINK).first()).toBeVisible();
    const listing = await openActions(page);
    expect(listing.status()).toBe(200);
    await page.getByText("Guest callback").first().click();
    await expect(page.getByText(seed().guest_phone)).toBeVisible();
    await expect(page.getByRole("button", { name: "Assign to me" })).toBeVisible();
  });
}

test("member with both capabilities can assign an action to themselves", async ({
  page,
}) => {
  await login(page, "member_both");
  await openActions(page);
  await page.getByText("Guest callback").first().click();
  const assigned = page.waitForResponse((response) =>
    response.url().endsWith(`/api/v1/actions/${seed().action_id}/assign`),
  );
  await page.getByRole("button", { name: "Assign to me" }).click();
  const response = await assigned;
  expect(response.status()).toBe(200);
  const body = await response.json();
  expect(body.data.status).toBe("ASSIGNED");
  expect(body.data.details_visible).toBe(true);
});

test("member with action.read only sees actions but cannot operate", async ({
  page,
}) => {
  await login(page, "member_read");
  await expect(page.locator(ACTIONS_LINK).first()).toBeVisible();
  const listing = await openActions(page);
  expect(listing.status()).toBe(200);
  await page.getByText("Guest callback").first().click();
  await expect(page.getByText(seed().guest_phone)).toBeVisible();
  await expect(
    page.getByText("Changing actions requires the action.operate permission."),
  ).toBeVisible();
  await expect(page.getByRole("button", { name: "Assign to me" })).toHaveCount(0);
});

for (const account of ["member_none", "member_operate"]) {
  test(`${account} cannot see actions or guest data`, async ({ page }) => {
    await login(page, account);
    await expect(page.locator(ACTIONS_LINK)).toHaveCount(0);
    const listing = await openActions(page);
    // The API is the boundary: the list is refused, so no guest data reaches
    // the browser even when the page is opened directly.
    expect(listing.status()).toBe(403);
    expect(await listing.text()).not.toContain(seed().guest_phone);
    await expect(page.getByText("Unable to load actions.")).toBeVisible();
    await expect(page.getByText(seed().guest_phone)).toHaveCount(0);
  });
}
