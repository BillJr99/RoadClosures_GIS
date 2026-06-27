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
    {
      scenario_id: "scenario-inactive",
      name: "Inactive Scenario",
      lat: 40.212,
      lon: -75.302,
      incident_radius_ft: 300,
      study_radius_ft: 2500,
      hose_max_ft: 500,
      reviewer_notes: "",
      expected_hydrant_hint: "",
      expected_closure_hint: "",
      status: "inactive",
      updated_at: "2026-06-23T00:00:00Z",
    },
  ];
  let buildCalled = false;
  let planCalled = false;
  let lastPlanBody: Record<string, unknown> | null = null;
  let scenarioRunCalled = false;
  let promoteCalled = false;
  let savedGolden: Record<string, unknown> | null = null;

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
  await page.route("**/api/scenarios/scenario-inactive", async (route) => {
    if (route.request().method() === "PUT") {
      const body = route.request().postDataJSON();
      const updated = { ...body, scenario_id: "scenario-inactive", updated_at: "2026-06-23T00:01:00Z" };
      scenarios = scenarios.map((scenario) => (scenario.scenario_id === "scenario-inactive" ? updated : scenario));
      await route.fulfill({ json: updated });
      return;
    }
    await route.fallback();
  });
  await page.route("**/api/scenarios/scenario-new/run", async (route) => {
    scenarioRunCalled = true;
    await new Promise((resolve) => setTimeout(resolve, 100));
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
  await page.route("**/api/scenarios/scenario-new/golden", async (route) => {
    if (route.request().method() === "PUT") {
      savedGolden = route.request().postDataJSON();
      await route.fulfill({
        json: {
          ...savedGolden,
          scenario_id: "scenario-new",
          updated_at: "2026-06-24T00:00:00Z",
        },
      });
      return;
    }
    await route.fulfill({
      json: savedGolden
        ? { ...savedGolden, scenario_id: "scenario-new", updated_at: "2026-06-24T00:00:00Z" }
        : {
            scenario_id: "scenario-new",
            reviewer: "",
            reviewed_at: "",
            expected_hydrant: { name: "", source: "", source_id: "", notes: "" },
            expected_closures: [],
            expected_warning_signs: [],
            notes: "",
            updated_at: "",
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
  await page.route("**/api/jobs/build?include_graph=true", async (route) => {
    buildCalled = true;
    await route.fulfill({ json: { job_id: "build-job-1", status: "pending" } });
  });
  await page.route("**/api/jobs/build-job-1", async (route) => {
    await route.fulfill({ json: { job_id: "build-job-1", status: "done", result: { roads: { roads: 1 }, hydrants: { reconciled: 1 } }, error: null } });
  });
  await page.route("**/api/plan", async (route) => {
    planCalled = true;
    lastPlanBody = route.request().postDataJSON();
    await new Promise((resolve) => setTimeout(resolve, 100));
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
              properties: { rank: 1, deployment_priority: 1, deployment_label: "P1", name: "Main St", reason: "Minimum cut closure edge", capacity: 3.2, sightline: "good" },
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
              properties: { kind: "warning_sign", sequence: "A", mutcd_sign_code: "W20-3", deployment_priority: 1, deployment_label: "P1A", approach_road: "Main St", distance_from_closure_ft: 100, placement_status: "placed" },
            },
          ],
        },
        graph_source: { cache_hit: true, cache_key: "test" },
        ranked_closures: [{ rank: 1, deployment_priority: 1, deployment_label: "P1", name: "Main St", reason: "Minimum cut closure edge", capacity: 3.2, sightline: "good", county_st_name: "Main St", county_match_confidence: 0.9 }],
        hydrant_candidates: [],
        run_id: "adhoc-20260624T120001Z",
        scenario_id: "adhoc-20260624T120001Z",
        report_path: "data/scenario_runs/adhoc-20260624T120001Z/report.html",
      },
    });
  });

  await page.goto("/");
  await expect(page.locator("header p").filter({ hasText: /roads, 1 hydrants/i })).toBeVisible();
  const inactiveRow = page.locator(".scenario-row").filter({ hasText: "Inactive Scenario" });
  await expect(inactiveRow).toHaveCount(0);
  await page.getByRole("button", { name: /Inactive Scenarios/i }).click();
  await expect(inactiveRow).toBeVisible();
  await expect(inactiveRow.getByRole("button", { name: /Run disabled/i })).toBeDisabled();
  await expect(inactiveRow.getByTitle(/Inactive scenarios cannot start/i)).toBeDisabled();
  await inactiveRow.getByTitle("Make active").click();
  await expect(page.locator(".scenario-row").filter({ hasText: "Inactive Scenario" }).getByTitle("Run scenario")).toBeVisible();

  await page.getByPlaceholder("Address or place").fill("123 Main St");
  await page.getByTitle("Search address").click();
  await expect(page.getByText("40.215000, -75.305000")).toBeVisible();
  await page.getByRole("button", { name: /Configuration/i }).click();
  await page.getByLabel("Hose envelope feet").fill("650");
  await page.getByLabel("Study radius feet").fill("1800");
  await page.getByLabel("Maximum sign distance feet").fill("900");
  await page.getByTitle("Save configuration").click();
  await expect(page.locator(".toast").filter({ hasText: /Configuration saved/i })).toBeVisible();

  await page.getByPlaceholder("Scenario name").fill("Test Scenario");
  await page.getByLabel("Reviewer note: expected hydrant").fill("blue hydrant");
  await page.getByLabel("Reviewer note: expected closure").fill("Main St");
  await page.getByTitle("Save scenario").click();
  await expect(page.locator(".scenario-row").filter({ hasText: "Test Scenario" })).toBeVisible();

  await page.getByTitle("Edit scenario").last().click();
  await page.getByPlaceholder("Scenario name").fill("Edited Scenario");
  await page.getByTitle("Update scenario").click();
  await expect(page.locator(".scenario-row").filter({ hasText: "Edited Scenario" })).toBeVisible();
  await page.getByPlaceholder("Reviewer").fill("Chief Reviewer");
  await page.getByPlaceholder("Expected hydrant name").fill("Hydrant 1");
  await page.getByPlaceholder("Hydrant source", { exact: true }).fill("OSM");
  await page.getByPlaceholder("Hydrant source ID").fill("hydrant-1");
  await page.getByPlaceholder(/Expected closures/i).fill("Main St | close through traffic | cones at intersection");
  await page.getByPlaceholder(/Expected warning signs/i).fill("Main St | Road Closed Ahead | 100 | north approach");
  await page.getByTitle("Save Golden JSON").click();
  await expect(page.getByText(/Golden saved for scenario-new/i)).toBeVisible();
  expect(savedGolden?.expected_closures).toEqual([
    { road: "Main St", reason: "close through traffic", notes: "cones at intersection" },
  ]);

  const editedRow = page.locator(".scenario-row").filter({ hasText: "Edited Scenario" });
  await editedRow.getByTitle("Load scenario").click();
  await expect(page.getByText(/Loaded scenario and centered map: Edited Scenario/i)).toBeVisible();
  await editedRow.getByTitle("Run scenario").click();
  await expect(page.getByText(/Running Edited Scenario/i)).toBeVisible();
  await expect(page.locator(".toast").filter({ hasText: /Running scenario: Edited Scenario/i })).toBeVisible();
  await expect(page.getByText(/Scenario run: 1 result/i)).toBeVisible();
  await expect(page.locator(".toast").filter({ hasText: /Scenario ready: Edited Scenario/i })).toBeVisible();
  await expect(page.getByText(/Map: incident pin in red/i)).toBeVisible();
  await expect(page.locator(".map-legend").getByText("Hose path", { exact: true })).toBeVisible();
  await expect(page.locator(".map-legend").getByText("Selected hydrant", { exact: true })).toBeVisible();
  expect(scenarioRunCalled).toBe(true);

  await page.getByRole("button", { name: /Show on map/i }).first().click();
  await expect(page.getByText(/MUTCD advisory signs/i)).toBeVisible();
  await expect(page.getByText(/Hose 300 ft/i)).toBeVisible();
  await page.getByTitle("Promote run").click();
  await page.getByTitle("Promote run").click();
  await expect(page.getByText(/Promoted 1 scenario summaries/i)).toBeVisible();
  expect(promoteCalled).toBe(true);

  await editedRow.getByTitle("Delete scenario").click();
  await expect(page.getByText(/Click delete again to confirm scenario removal/i)).toBeVisible();
  await editedRow.getByTitle("Delete scenario").click();
  await expect(page.locator("section").filter({ hasText: "Scenarios" }).locator(".scenario-row").filter({ hasText: "Edited Scenario" })).toHaveCount(0);

  await page.getByLabel("Name", { exact: true }).fill("Known Hydrant");
  await page.getByTitle("Pick manual hydrant location on map").click();
  await expect(page.locator(".toast").filter({ hasText: /Click the map to fill manual hydrant/i })).toBeVisible();
  await page.getByPlaceholder("Lat").fill("40.216");
  await page.getByPlaceholder("Lon").fill("-75.306");
  await page.getByTitle("Add manual hydrant").click();
  await expect(page.getByText("Known Hydrant")).toBeVisible();
  await page.getByTitle("Remove").click();
  await expect(page.getByText("Known Hydrant")).toHaveCount(0);

  await page.getByRole("button", { name: "Build From Sources" }).click();
  expect(buildCalled).toBe(true);

  await page.getByRole("button", { name: /Recommend Closures/i }).click();
  await expect(page.locator(".toast").filter({ hasText: /Running closure recommendations/i })).toBeVisible();
  await expect(page.locator(".inline-status").filter({ hasText: /Plan ready/i })).toBeVisible();
  await expect(page.locator(".toast").filter({ hasText: /Recommendations ready/i })).toBeVisible();
  await expect(page.getByText(/Recommendation run: 1 result/i)).toBeVisible();
  await expect(page.getByText(/Recommendation summary/i)).toBeVisible();
  await expect(page.getByText(/drawn in red on the map/i)).toBeVisible();
  await expect(page.getByText("#1 Main St")).toBeVisible();
  await expect(page.locator(".closure .priority-badge").filter({ hasText: "P1" }).first()).toBeVisible();
  await expect(page.locator(".priority-badge").filter({ hasText: "P1A" })).toBeVisible();
  expect(planCalled).toBe(true);
  expect(lastPlanBody?.hydrant_count).toBe(1);
  expect(lastPlanBody?.hose_max_ft).toBe(650);
  expect(lastPlanBody?.study_radius_ft).toBe(1800);
  expect(lastPlanBody?.sign_max_distance_ft).toBe(900);

  await page.getByRole("button", { name: /Add Hydrant/i }).click();
  await expect(page.locator(".toast").filter({ hasText: /Recommendations ready/i })).toBeVisible();
  expect(lastPlanBody?.hydrant_count).toBe(2);

  await page.getByRole("button", { name: /Clear Incident/i }).click();
  await expect(page.getByText(/Remove this incident and clear recommendations/i)).toBeVisible();
  await page.getByRole("button", { name: /Remove/i }).click();
  await expect(page.getByText(/Incident removed/i)).toBeVisible();
});
