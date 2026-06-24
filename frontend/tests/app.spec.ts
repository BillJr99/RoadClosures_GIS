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
  let scenarios: Array<Record<string, unknown>> = [
    {
      scenario_id: "scenario-test",
      name: "Existing Scenario",
      lat: 40.212,
      lon: -75.302,
      incident_radius_ft: 300,
      study_radius_ft: 2500,
      hose_max_ft: 500,
      reviewer_notes: "",
      expected_hydrant_hint: "blue hydrant",
      expected_closure_hint: "Main St",
      status: "active",
      updated_at: "2026-06-23T00:00:00Z",
    },
  ];
  let buildCalled = false;
  let planCalled = false;
  let scenarioRunCalled = false;
  let promoteCalled = false;

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
  await page.route("**/api/scenarios", async (route) => {
    if (route.request().method() === "GET") {
      await route.fulfill({ json: scenarios });
      return;
    }
    const body = route.request().postDataJSON();
    const created = { ...body, scenario_id: "scenario-new", updated_at: "2026-06-23T00:00:00Z" };
    scenarios = [...scenarios, created];
    await route.fulfill({ status: 201, json: created });
  });
  await page.route("**/api/scenarios/scenario-new", async (route) => {
    if (route.request().method() === "PUT") {
      const body = route.request().postDataJSON();
      const updated = { ...body, scenario_id: "scenario-new", updated_at: "2026-06-23T00:01:00Z" };
      scenarios = scenarios.map((scenario) => (scenario.scenario_id === "scenario-new" ? updated : scenario));
      await route.fulfill({ json: updated });
      return;
    }
    if (route.request().method() === "DELETE") {
      scenarios = scenarios.filter((scenario) => scenario.scenario_id !== "scenario-new");
      await route.fulfill({ status: 204, body: "" });
      return;
    }
    await route.fallback();
  });
  await page.route("**/api/scenarios/scenario-new/run", async (route) => {
    scenarioRunCalled = true;
    await route.fulfill({
      json: {
        run_dir: "data/scenario_runs/20260624T120000Z",
        report_path: "data/scenario_runs/20260624T120000Z/report.html",
        results: [
          {
            scenario_id: "scenario-new",
            name: "Edited Scenario",
            status: "passed",
            golden_status: "missing",
            differences: ["No golden summary exists yet"],
          },
        ],
      },
    });
  });
  await page.route("**/api/scenario-runs", async (route) => {
    await route.fulfill({
      json: [
        {
          run_id: "20260624T120000Z",
          report_path: "data/scenario_runs/20260624T120000Z/report.html",
          result_count: 1,
          failed_count: 0,
          changed_count: 0,
          missing_count: 1,
        },
      ],
    });
  });
  await page.route("**/api/scenario-runs/20260624T120000Z", async (route) => {
    await route.fulfill({
      json: {
        run_id: "20260624T120000Z",
        run_dir: "data/scenario_runs/20260624T120000Z",
        report_path: "data/scenario_runs/20260624T120000Z/report.html",
        results: [
          {
            scenario_id: "scenario-new",
            name: "Edited Scenario",
            status: "passed",
            golden_status: "missing",
            differences: ["No golden summary exists yet"],
          },
        ],
      },
    });
  });
  await page.route("**/api/scenario-runs/20260624T120000Z/scenarios/scenario-new", async (route) => {
    await route.fulfill({
      json: {
        scenario: {
          scenario_id: "scenario-new",
          name: "Edited Scenario",
          lat: 40.215,
          lon: -75.305,
          incident_radius_ft: 300,
          study_radius_ft: 2500,
          hose_max_ft: 500,
          reviewer_notes: "",
          expected_hydrant_hint: "",
          expected_closure_hint: "",
          status: "active",
          updated_at: "2026-06-23T00:00:00Z",
        },
        plan: {
          cut_value: 3.2,
          selected_hydrant: hydrants.features[0],
          hose_route: {
            type: "Feature",
            geometry: { type: "LineString", coordinates: [[-75.305, 40.215], [-75.304, 40.216]] },
            properties: { length_ft: 300, curvature: 0.11, elevation_change_ft: 5, max_grade: 0.02 },
          },
          closures: { type: "FeatureCollection", features: [] },
          overlays: { type: "FeatureCollection", features: [] },
          warning_signs: {
            type: "FeatureCollection",
            features: [
              {
                type: "Feature",
                geometry: { type: "Point", coordinates: [-75.308, 40.214] },
                properties: { kind: "warning_sign", sequence: "A", approach_road: "Main St", distance_from_closure_ft: 100, placement_status: "placed" },
              },
            ],
          },
          graph_source: { cache_hit: true, cache_key: "test" },
          ranked_closures: [{ rank: 1, name: "Main St", reason: "Minimum cut closure edge", capacity: 3.2, sightline: "good" }],
          hydrant_candidates: [],
        },
      },
    });
  });
  await page.route("**/api/scenario-runs/20260624T120000Z/promote", async (route) => {
    promoteCalled = true;
    await route.fulfill({ json: { run_id: "20260624T120000Z", promoted_count: 1 } });
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
          properties: { length_ft: 300, curvature: 0.11, elevation_change_ft: 5, max_grade: 0.02 },
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
        warning_signs: {
          type: "FeatureCollection",
          features: [
            {
              type: "Feature",
              geometry: { type: "Point", coordinates: [-75.308, 40.214] },
              properties: { kind: "warning_sign", sequence: "A", approach_road: "Main St", distance_from_closure_ft: 100, placement_status: "placed" },
            },
          ],
        },
        graph_source: { cache_hit: true, cache_key: "test" },
        ranked_closures: [{ rank: 1, name: "Main St", reason: "Minimum cut closure edge", capacity: 3.2, sightline: "good", county_st_name: "Main St", county_match_confidence: 0.9 }],
        hydrant_candidates: [],
      },
    });
  });

  await page.goto("/");
  await expect(page.getByText(/roads, 1 hydrants/i)).toBeVisible();

  await page.getByPlaceholder("Address or place").fill("123 Main St");
  await page.getByTitle("Search address").click();
  await expect(page.getByText("40.215000, -75.305000")).toBeVisible();

  await page.getByPlaceholder("Scenario name").fill("Test Scenario");
  await page.getByPlaceholder("Expected hydrant hint").fill("blue hydrant");
  await page.getByPlaceholder("Expected closure hint").fill("Main St");
  await page.getByTitle("Save scenario").click();
  await expect(page.locator(".scenario-row").filter({ hasText: "Test Scenario" })).toBeVisible();

  await page.getByTitle("Edit scenario").last().click();
  await page.getByPlaceholder("Scenario name").fill("Edited Scenario");
  await page.getByTitle("Update scenario").click();
  await expect(page.locator(".scenario-row").filter({ hasText: "Edited Scenario" })).toBeVisible();

  await page.getByTitle("Load scenario").last().click();
  await expect(page.getByText(/Loaded scenario: Edited Scenario/i)).toBeVisible();
  await page.getByTitle("Run scenario").last().click();
  await expect(page.getByText(/Last scenario run/i)).toBeVisible();
  expect(scenarioRunCalled).toBe(true);

  await page.getByTitle("Review run").click();
  await expect(page.getByText(/Review 20260624T120000Z/i)).toBeVisible();
  await page.getByRole("button", { name: /Edited Scenario: passed/i }).click();
  await expect(page.getByText(/MUTCD advisory signs/i)).toBeVisible();
  await expect(page.getByText(/Hose 300 ft/i)).toBeVisible();
  await page.getByTitle("Promote run").click();
  await page.getByTitle("Promote run").click();
  await expect(page.getByText(/Promoted 1 scenario summaries/i)).toBeVisible();
  expect(promoteCalled).toBe(true);

  await page.getByTitle("Delete scenario").last().click();
  await expect(page.locator(".scenario-row").filter({ hasText: "Edited Scenario" })).toHaveCount(0);

  await page.getByPlaceholder("Name", { exact: true }).fill("Known Hydrant");
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
