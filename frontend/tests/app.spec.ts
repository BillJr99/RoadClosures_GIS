import { expect, test } from "@playwright/test";

const roads = {
  type: "FeatureCollection",
  features: [
    {
      type: "Feature",
      geometry: { type: "LineString", coordinates: [[-75.31, 40.21], [-75.30, 40.22]] },
      properties: { name: "Main St" },
    },
  ],
};

const hydrants = {
  type: "FeatureCollection",
  features: [
    {
      type: "Feature",
      geometry: { type: "Point", coordinates: [-75.305, 40.215] },
      properties: { source: "OSM", flow_class: "blue" },
    },
  ],
};

test("exercises incident planning, geocoding, manual hydrants, layer rebuild, and overlays", async ({ page }) => {
  let manualHydrants: Array<Record<string, unknown>> = [];
  let buildCalled = false;
  let planCalled = false;

  await page.route("**/api/layers/roads", async (route) => {
    await route.fulfill({ json: roads });
  });
  await page.route("**/api/layers/hydrants", async (route) => {
    await route.fulfill({ json: hydrants });
  });
  await page.route("**/api/manual-hydrants", async (route) => {
    if (route.request().method() === "GET") {
      await route.fulfill({ json: manualHydrants });
      return;
    }
    const body = route.request().postDataJSON();
    const created = { ...body, manual_id: "manual-test", updated_at: "2026-06-23T00:00:00Z" };
    manualHydrants = [created];
    await route.fulfill({ status: 201, json: created });
  });
  await page.route("**/api/manual-hydrants/manual-test", async (route) => {
    manualHydrants = [];
    await route.fulfill({ status: 204, body: "" });
  });
  await page.route("**/api/geocode?q=*", async (route) => {
    await route.fulfill({
      json: [{ label: "123 Main St, Montgomery County", lat: 40.215, lon: -75.305 }],
    });
  });
  await page.route("**/api/layers/build?include_graph=true", async (route) => {
    buildCalled = true;
    await route.fulfill({ json: { roads: { roads: 1 }, hydrants: { reconciled: 1 } } });
  });
  await page.route("**/api/plan", async (route) => {
    planCalled = true;
    await route.fulfill({
      json: {
        cut_value: 3.2,
        selected_hydrant: hydrants.features[0],
        hose_route: {
          type: "Feature",
          geometry: { type: "LineString", coordinates: [[-75.305, 40.215], [-75.304, 40.216]] },
          properties: { length_ft: 300 },
        },
        closures: {
          type: "FeatureCollection",
          features: [
            {
              type: "Feature",
              geometry: { type: "LineString", coordinates: [[-75.306, 40.214], [-75.307, 40.215]] },
              properties: { rank: 1, name: "Main St", reason: "Minimum cut closure edge", capacity: 3.2, sightline: "good" },
            },
          ],
        },
        overlays: {
          type: "FeatureCollection",
          features: [
            hydrants.features[0],
            {
              type: "Feature",
              geometry: { type: "LineString", coordinates: [[-75.306, 40.214], [-75.307, 40.215]] },
              properties: { rank: 1, name: "Main St" },
            },
          ],
        },
        ranked_closures: [{ rank: 1, name: "Main St", reason: "Minimum cut closure edge", capacity: 3.2, sightline: "good" }],
        hydrant_candidates: [],
      },
    });
  });

  await page.goto("/");
  await expect(page.getByText(/roads, 1 hydrants/i)).toBeVisible();

  await page.getByPlaceholder("Address or place").fill("123 Main St");
  await page.getByTitle("Search address").click();
  await expect(page.getByText("40.215000, -75.305000")).toBeVisible();

  await page.getByPlaceholder("Name").fill("Known Hydrant");
  await page.getByPlaceholder("Lat").fill("40.216");
  await page.getByPlaceholder("Lon").fill("-75.306");
  await page.getByTitle("Add manual hydrant").click();
  await expect(page.getByText("Known Hydrant")).toBeVisible();
  await page.getByTitle("Remove").click();
  await expect(page.getByText("Known Hydrant")).toHaveCount(0);

  await page.getByRole("button", { name: "Build From Sources" }).click();
  expect(buildCalled).toBe(true);

  await page.getByRole("button", { name: /Recommend Closures/i }).click();
  await expect(page.getByText(/Plan ready/i)).toBeVisible();
  await expect(page.getByText("#1 Main St")).toBeVisible();
  expect(planCalled).toBe(true);
});

