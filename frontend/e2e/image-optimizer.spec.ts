import { expect, test } from "@playwright/test";

// The image optimizer may only fetch statically imported media. Every other
// source, local or remote, is refused at validation, before any fetch.

const optimize = (url: string, width = 64) =>
  `/_next/image?url=${encodeURIComponent(url)}&w=${width}&q=75`;

const NOT_ALLOWED = '"url" parameter is not allowed';

const refusedLocal = [
  "/api/v1/auth/me",
  "/api/v1/health",
  "/robots.txt",
  "/login",
  // Traversal out of the allowed prefix, literal and percent-encoded dots.
  "/_next/static/media/../../api/v1/auth/me",
  "/_next/static/media/%2e%2e/%2e%2e/api/v1/auth/me",
  // A query string is only allowed when a pattern names it exactly.
  "/_next/static/media/photo.png?v=1",
];

for (const source of refusedLocal) {
  test(`local source ${source} is refused before any fetch`, async ({ request }) => {
    const response = await request.get(optimize(source));
    expect(response.status()).toBe(400);
    expect(await response.text()).toContain(NOT_ALLOWED);
  });
}

const refusedOther = [
  "https://example.com/photo.png",
  "http://127.0.0.1:8100/health",
  "http://169.254.169.254/latest/meta-data/",
  "file:///etc/passwd",
  "//example.com/photo.png",
  "/_next/image?url=/robots.txt",
];

for (const source of refusedOther) {
  test(`source ${source} is refused`, async ({ request }) => {
    const response = await request.get(optimize(source));
    expect(response.status()).toBe(400);
  });
}

test("static media passes validation and is then looked up", async ({ request }) => {
  // No static media file has this name, so the lookup misses: a 404 here
  // (not a 400) shows the allowed prefix gets past the allowlist.
  const response = await request.get(optimize("/_next/static/media/missing-file.png"));
  expect(response.status()).toBe(404);
});

test("encoded slashes stay inside the media prefix and find nothing", async ({ request }) => {
  const response = await request.get(
    optimize("/_next/static/media/..%2f..%2fapi/v1/auth/me"),
  );
  expect([400, 404]).toContain(response.status());
  expect(response.status()).not.toBe(200);
});
