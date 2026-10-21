import { test, expect } from "@playwright/test";

const defect = {
  id: "synthetic-record-001",
  job_id: "job-001",
  defect_class: "pothole",
  confidence: 0.88,
  bbox: [0.2, 0.3, 0.5, 0.6],
  latitude: 12.981,
  longitude: 77.604,
  gps_uncertainty_m: 8,
  captured_at: "2026-10-01T12:00:00Z",
  severity: 72,
  explanation: {
    raw_score: 72,
    class_base: 40,
    image_area_ratio: 0.13,
    area_source: "bounding_box_proxy",
    calibration_version: null,
    measurement: "image-relative; not physical dimensions",
  },
  model_version: "synthetic-fixture-v1",
  synthetic: true,
  road_name: "MG Road",
  status: "new",
  critical_location: false,
  note: "",
  revision: 1,
  duplicate_candidate_id: null,
  merged_into_id: null,
  priority: 65,
  priority_reasons: { severity: 54, age: 11, critical_location: 0 },
  observations: [],
};
const second = {
  ...defect,
  id: "synthetic-record-002",
  defect_class: "alligator_cracking",
  road_name: "Residency Road",
  severity: 55,
  latitude: 12.976,
  longitude: 77.598,
};
const third = {
  ...defect,
  id: "synthetic-record-003",
  defect_class: "longitudinal_crack",
  road_name: "Cubbon Road",
  severity: 32,
  latitude: 12.987,
  longitude: 77.61,
};
const user = {
  id: "admin",
  username: "test-inspector",
  role: "admin",
  enabled: true,
};

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() =>
    sessionStorage.setItem("roadscope-token", "test-only-token"),
  );
  await page.route("**/api/**", async (route) => {
    const url = new URL(route.request().url()),
      path = url.pathname;
    let body: unknown = {};
    if (path === "/api/auth/me") body = user;
    else if (path === "/api/health") body = { status: "ok", demo_mode: true };
    else if (path === "/api/model")
      body = {
        status: "ready",
        version: "synthetic-fixture-v1",
        metrics: null,
        synthetic: true,
      };
    else if (path === "/api/defects")
      body = {
        items:
          url.searchParams.get("synthetic") === "false"
            ? []
            : [defect, second, third],
        total: url.searchParams.get("synthetic") === "false" ? 0 : 3,
      };
    else if (path.startsWith("/api/defects/"))
      body =
        route.request().method() === "PATCH"
          ? { ...defect, ...route.request().postDataJSON(), revision: 2 }
          : defect;
    else if (path === "/api/analytics")
      body = {
        total: 3,
        active: 3,
        synthetic: 3,
        high_severity: 1,
        observed_health: 47,
        health_method:
          "100 - mean active visual severity; not PCI; coverage unknown",
        by_class: { pothole: 1, alligator_cracking: 1, longitudinal_crack: 1 },
        by_status: { new: 3 },
        by_day: { "2026-10-01": 3 },
        priorities: [defect, second, third],
      };
    else if (path === "/api/jobs")
      body = route.request().method() === "POST" ? { id: "new-job" } : [];
    else if (path === "/api/users") body = [user];
    else if (path === "/api/reports/defects.csv") {
      await route.fulfill({
        contentType: "text/csv",
        body: "id,synthetic\nrecord,true\n",
      });
      return;
    }
    await route.fulfill({ json: body });
  });
});

test("map, inspection, review and source filters", async ({ page }) => {
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "A clearer view of your roads." }),
  ).toBeVisible();
  await expect(page.getByText("DEMO DATA", { exact: true })).toBeVisible();
  await page
    .getByRole("button", { name: "Inspect synthetic-record-001", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Inspection record" }),
  ).toBeVisible();
  await expect(page.getByText("Uncalibrated screening score")).toBeVisible();
  await page.getByLabel("Review status").selectOption("confirmed");
  await page.getByLabel("Inspection note").fill("Inspected by field team");
  await page.getByRole("button", { name: "Save review" }).click();
  await expect(page.getByText("Review saved to audit history.")).toBeVisible();
  await page.getByLabel("Data source").selectOption("false");
  await expect(page.getByText("No defects match these filters.")).toBeVisible();
});

test("analytics, export, upload form and navigation", async ({ page }) => {
  await page.goto("/");
  await page
    .getByRole("button", { name: "Analytics & reports", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Defect distribution" }),
  ).toBeVisible();
  await expect(
    page.getByText("No measured model accuracy is available.", {
      exact: false,
    }),
  ).toBeVisible();
  const download = page.waitForEvent("download");
  await page.getByRole("button", { name: "Export filtered report" }).click();
  expect((await download).suggestedFilename()).toBe("roadscope-defects.csv");
  await page.getByRole("button", { name: "New survey", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Bring the road into view" }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Access control", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Organization access" }),
  ).toBeVisible();
});

for (const width of [320, 375, 414, 768, 1440])
  test(`responsive layout at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 1000 });
    await page.goto("/");
    await expect(
      page.getByRole("heading", { name: "Road condition map" }),
    ).toBeVisible();
    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth > window.innerWidth,
    );
    expect(overflow).toBe(false);
    await page.screenshot({
      path: `test-results/dashboard-${width}.png`,
      fullPage: true,
    });
  });

test("login failure is visible and does not imply success", async ({
  page,
}) => {
  await page.addInitScript(() => sessionStorage.clear());
  await page.route("**/api/auth/token", (route) =>
    route.fulfill({ status: 401, json: { detail: "Invalid credentials" } }),
  );
  await page.goto("/");
  await page.getByLabel("Username").fill("wrong");
  await page.getByLabel("Password", { exact: true }).fill("wrong");
  await page.getByRole("button", { name: "Open workspace" }).click();
  await expect(page.getByRole("alert")).toContainText("Invalid credentials");
});
