import React from "react";
import ReactDOM from "react-dom/client";
import "leaflet/dist/leaflet.css";
import "./styles.css";

function App() {
  return (
    <main className="app-shell">
      <aside className="sidebar">
        <h1>Fire Police GIS</h1>
        <p>Incident planning map scaffold</p>
      </aside>
      <section className="map-panel">Map loading...</section>
    </main>
  );
}

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);

