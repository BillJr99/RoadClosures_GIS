import { expect, test } from "@playwright/test";

const pauseMs = Number(process.env.DEMO_STEP_MS ?? "1200");

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
      properties: { source: "OSM", flow_class: "blue", name: "Demo Hydrant" },
    },
  ],
};

async function step(page, label: string) {
  await page.getByText(/Fire Police GIS/i).waitFor();
  console.log(`DEMO: ${label}`);
  await page.waitForTimeout(pauseMs);
}

test("slow demonstration of the full fire police GIS workflow", async ({ page }) => {
  let manualHydrants: Array<Record<string, unknown>> = [];
  let scenarios: Array<Record<string, unknown>> = [
    {
      scenario_id: "scenario-demo",
      name: "Demo Scenario",
      lat: 40.215,
      lon: -75.305,
      incident_radius_ft: 300,
      study_radius_ft: 2500,
      hose_max_ft: 500,
      reviewer_notes: "Demonstration run",
      expected_hydrant_hint: "Demo Hydrant",
      expected_closure_hint: "Main St",
      status: "active",
      updated_at: "2026-06-24T00:00:00Z",
    },
  ];

  await page.route("**/api/layers/roads", async (route) => route.fulfill({ json: roads }));
  await page.route("**/api/layers/hydrants", async (route) => route.fulfill({ json: hydrants }));
  await page.route("**/api/manual-hydrants", async (route) => {
    if (route.request().method() === "GET") {
      await route.fulfill({ json: manualHydrants });
      return;
    }
    const body = route.request().postDataJSON();
    const created = { ...body, manual_id: "manual-demo", updated_at: "2026-06-24T00:00:00Z" };
    manualHydrants = [created];
    await route.fulfill({ status: 201, json: created });
  });
  await page.route("**/api/manual-hydrants/manual-demo", async (route) => {
    manualHydrants = [];
    await route.fulfill({ status: 204, body: "" });
  });
  await page.route("**/api/scenarios", async (route) => {
    if (route.request().method() === "GET") {
      await route.fulfill({ json: scenarios });
      return;
    }
    const body = route.request().postDataJSON();
    const created = { ...body, scenario_id: "scenario-created", updated_at: "2026-06-24T00:00:00Z" };
    scenarios = [...scenarios, created];
    await route.fulfill({ status: 201, json: created });
  });
  await page.route("**/api/scenarios/scenario-created/run", async (route) => {
    await route.fulfill({
      json: {
        run_dir: "data/scenario_runs/20260624T130000Z",
        report_path: "data/scenario_runs/20260624T130000Z/report.html",
        results: [
          {
            scenario_id: "scenario-created",
            name: "Demo Saved Incident",
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
          run_id: "20260624T130000Z",
          report_path: "data/scenario_runs/20260624T130000Z/report.html",
          result_count: 1,
          failed_count: 0,
          changed_count: 0,
          missing_count: 1,
        },
      ],
    });
  });
  await page.route("**/api/scenario-runs/20260624T130000Z", async (route) => {
    await route.fulfill({
      json: {
        run_id: "20260624T130000Z",
        run_dir: "data/scenario_runs/20260624T130000Z",
        report_path: "data/scenario_runs/20260624T130000Z/report.html",
        results: [
          {
            scenario_id: "scenario-created",
            name: "Demo Saved Incident",
            status: "passed",
            golden_status: "missing",
            differences: ["No golden summary exists yet"],
          },
        ],
      },
    });
  });
  await page.route("**/api/scenario-runs/20260624T130000Z/scenarios/scenario-created", async (route) => {
    await route.fulfill({ json: { scenario: scenarios.at(-1), plan: demoPlan() } });
  });
  await page.route("**/api/scenario-runs/20260624T130000Z/promote", async (route) => {
    await route.fulfill({ json: { run_id: "20260624T130000Z", promoted_count: 1 } });
  });
  await page.route("**/api/geocode?q=*", async (route) => {
    await route.fulfill({ json: [{ label: "123 Main St, Montgomery County", lat: 40.215, lon: -75.305 }] });
  });
  await page.route("**/api/layers/build?include_graph=true", async (route) => {
    await route.fulfill({ json: { roads: { roads: 1 }, hydrants: { reconciled: 1 } } });
  });
  await page.route("**/api/plan", async (route) => route.fulfill({ json: demoPlan() }));

  await page.goto("/");
  await step(page, "Loaded roads, hydrants, scenarios, and recent scenario runs.");

  await page.getByPlaceholder("Address or place").fill("123 Main St");
  await step(page, "Typed an incident address.");
  await page.getByTitle("Search address").click();
  await expect(page.locator(".coords").getByText("40.215000, -75.305000")).toBeVisible();
  await step(page, "Geocoded the incident and placed it on the map.");

  await page.getByPlaceholder("Scenario name").fill("Demo Saved Incident");
  await page.getByPlaceholder("Expected hydrant hint").fill("Demo Hydrant");
  await page.getByPlaceholder("Expected closure hint").fill("Main St");
  await step(page, "Filled out a scenario from the incident.");
  await page.getByTitle("Save scenario").click();
  await expect(page.locator(".scenario-row").filter({ hasText: "Demo Saved Incident" })).toBeVisible();
  await step(page, "Saved the scenario to the CSV-backed store.");

  await page.getByTitle("Run scenario").last().click();
  await expect(page.getByText(/Scenario run complete/i)).toBeVisible();
  await step(page, "Ran the scenario validation path.");

  await page.getByTitle("Review run").first().click();
  await expect(page.getByText(/Review 20260624T130000Z/i)).toBeVisible();
  await step(page, "Opened the scenario run review panel.");
  await page.getByRole("button", { name: /Demo Saved Incident: passed/i }).click();
  await expect(page.getByText(/MUTCD advisory signs/i)).toBeVisible();
  await step(page, "Loaded saved plan overlays, closure ranking, and warning sign candidates.");

  await page.getByTitle("Promote run").first().click();
  await step(page, "Armed the two-step promotion control after review.");
  await page.getByTitle("Promote run").first().click();
  await expect(page.getByText(/Promoted 1 scenario summaries/i)).toBeVisible();
  await step(page, "Promoted the accepted scenario summary to goldens.");

  await page.getByPlaceholder("Name", { exact: true }).fill("Known Hydrant");
  await page.getByPlaceholder("Lat").fill("40.216");
  await page.getByPlaceholder("Lon").fill("-75.306");
  await step(page, "Entered a manually known hydrant.");
  await page.getByTitle("Add manual hydrant").click();
  await expect(page.getByText("Known Hydrant")).toBeVisible();
  await step(page, "Added the manual hydrant.");
  await page.getByTitle("Remove").click();
  await step(page, "Removed the manual hydrant.");

  await page.getByRole("button", { name: /Recommend Closures/i }).click();
  await expect(page.getByText("#1 Main St")).toBeVisible();
  await step(page, "Generated the min-cut closure recommendation and MUTCD advisory sign layer.");
});

function demoPlan() {
  return {
    cut_value: 3.2,
    selected_hydrant: hydrants.features[0],
    hose_route: {
      type: "Feature",
      geometry: { type: "LineString", coordinates: [[-75.305, 40.215], [-75.304, 40.216]] },
      properties: { length_ft: 300, curvature: 0.12, elevation_change_ft: 4 },
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
    overlays: { type: "FeatureCollection", features: [] },
    warning_signs: {
      type: "FeatureCollection",
      features: [
        {
          type: "Feature",
          geometry: { type: "Point", coordinates: [-75.308, 40.214] },
          properties: { kind: "warning_sign", sequence: "A", sign_label: "ROAD CLOSED AHEAD" },
        },
      ],
    },
    graph_source: { cache_hit: true, cache_key: "demo" },
    ranked_closures: [
      {
        rank: 1,
        name: "Main St",
        reason: "Minimum cut closure edge",
        capacity: 3.2,
        sightline: "good",
        county_st_name: "Main St",
        county_match_confidence: 0.9,
      },
    ],
    hydrant_candidates: [],
  };
}
