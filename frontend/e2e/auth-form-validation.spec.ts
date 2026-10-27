import { expect, test, type Page, type Request } from "@playwright/test";

// Client-side validation of the four auth forms (Zod schemas through the
// react-hook-form resolver). Invalid input must show the field message and
// send nothing; valid input must reach the API. API calls that a valid form
// makes are answered by route mocks, so no account or backend state is used.

const AUTH_API = /\/api\/v1\/auth\//;

async function openForm(page: Page, path: string): Promise<Request[]> {
  await page.context().addCookies([
    { name: "NEXT_LOCALE", value: "en", url: "http://localhost:3100" },
  ]);
  const requests: Request[] = [];
  page.on("request", (request) => {
    if (AUTH_API.test(new URL(request.url()).pathname)) requests.push(request);
  });
  await page.goto(path);
  return requests;
}

async function rejectWith(page: Page, endpoint: string) {
  await page.route(`**/api/v1/auth/${endpoint}`, (route) =>
    route.fulfill({
      status: 400,
      contentType: "application/json",
      body: JSON.stringify({
        success: false,
        message: "Rejected by test",
        data: null,
        error: { code: "TEST_REJECTED", message: "Rejected by test" },
      }),
    }),
  );
}

const submit = (page: Page) => page.locator('form button[type="submit"]').click();

test("login form validates email and password before calling the API", async ({ page }) => {
  const requests = await openForm(page, "/login");
  await submit(page);
  await expect(page.getByText("Please enter your email")).toBeVisible();
  await expect(page.getByText("Password is required")).toBeVisible();

  await page.locator("#email").fill("not-an-email");
  await page.locator("#password").fill("anything");
  await submit(page);
  await expect(page.getByText("Enter a valid email address")).toBeVisible();
  expect(requests).toHaveLength(0);

  await rejectWith(page, "login");
  await page.locator("#email").fill("someone@example.com");
  const sent = page.waitForRequest((request) => request.url().endsWith("/auth/login"));
  await submit(page);
  expect((await sent).postDataJSON()).toMatchObject({ email: "someone@example.com" });
});

test("register form validates name, email and password length", async ({ page }) => {
  const requests = await openForm(page, "/register");
  await page.locator("#full_name").fill("   ");
  await submit(page);
  await expect(page.getByText("Please enter your name")).toBeVisible();
  await expect(page.getByText("Please enter your email")).toBeVisible();
  await expect(page.getByText("Password must be at least 8 characters")).toBeVisible();

  await page.locator("#full_name").fill("Guest Owner");
  await page.locator("#email").fill("owner@");
  await page.locator("#password").fill("1234567");
  await submit(page);
  await expect(page.getByText("Enter a valid email address")).toBeVisible();
  await expect(page.getByText("Password must be at least 8 characters")).toBeVisible();
  expect(requests).toHaveLength(0);

  await rejectWith(page, "register");
  await page.locator("#email").fill("owner@example.com");
  await page.locator("#password").fill("12345678");
  const sent = page.waitForRequest((request) => request.url().endsWith("/auth/register"));
  await submit(page);
  // The trimmed name is what the schema hands to the API.
  expect((await sent).postDataJSON()).toMatchObject({
    full_name: "Guest Owner",
    email: "owner@example.com",
  });
});

test("forgot-password form validates the email", async ({ page }) => {
  const requests = await openForm(page, "/forgot-password");
  await submit(page);
  await expect(page.getByText("Please enter your email")).toBeVisible();
  await page.locator("#email").fill("missing-at.example.com");
  await submit(page);
  await expect(page.getByText("Enter a valid email address")).toBeVisible();
  expect(requests).toHaveLength(0);

  await rejectWith(page, "forgot-password");
  await page.locator("#email").fill("someone@example.com");
  const sent = page.waitForRequest((request) =>
    request.url().endsWith("/auth/forgot-password"),
  );
  await submit(page);
  expect((await sent).postDataJSON()).toMatchObject({ email: "someone@example.com" });
});

test("reset-password form validates length and confirmation", async ({ page }) => {
  await page.addInitScript(() => {
    window.sessionStorage.setItem(
      "oneflow_password_reset",
      JSON.stringify({ email: "someone@example.com", resendAvailableAt: Date.now() }),
    );
  });
  await page.route("**/api/v1/auth/verify-password-reset", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        success: true,
        message: "OK",
        data: { reset_token: "test-reset-token" },
        error: null,
      }),
    }),
  );
  await openForm(page, "/reset-password");
  await page.locator("#reset-code").fill("123456");
  await submit(page);
  await expect(page.locator("#new_password")).toBeVisible();

  const resets: Request[] = [];
  page.on("request", (request) => {
    if (request.url().endsWith("/auth/reset-password")) resets.push(request);
  });

  await submit(page);
  await expect(page.getByText("Password must be at least 8 characters")).toBeVisible();
  await expect(page.getByText("Password is required")).toBeVisible();

  await page.locator("#new_password").fill("long-enough-1");
  await page.locator("#confirm_password").fill("long-enough-2");
  await submit(page);
  await expect(page.getByText("Passwords do not match")).toBeVisible();

  // Over the 128-character maximum: the field shows an error (Zod's default
  // wording, which a major upgrade changes) and nothing is sent.
  await page.locator("#new_password").fill("x".repeat(129));
  await page.locator("#confirm_password").fill("x".repeat(129));
  await submit(page);
  await expect(page.locator("#new_password ~ p")).toBeVisible();
  expect(resets).toHaveLength(0);

  await rejectWith(page, "reset-password");
  await page.locator("#new_password").fill("long-enough-1");
  await page.locator("#confirm_password").fill("long-enough-1");
  const sent = page.waitForRequest((request) => request.url().endsWith("/auth/reset-password"));
  await submit(page);
  expect((await sent).postDataJSON()).toMatchObject({
    reset_token: "test-reset-token",
    new_password: "long-enough-1",
  });
});
