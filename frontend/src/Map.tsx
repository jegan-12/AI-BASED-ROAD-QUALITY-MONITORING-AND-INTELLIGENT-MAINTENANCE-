import { useEffect, useState } from "react";
import {
  MapContainer,
  TileLayer,
  CircleMarker,
  Tooltip,
  useMap,
  useMapEvents,
} from "react-leaflet";
import { Crosshair } from "lucide-react";
import type { Defect } from "./types";
import { label } from "./types";
import "leaflet/dist/leaflet.css";

function Controls({
  selected,
  items,
  onBounds,
}: {
  selected: Defect | null;
  items: Defect[];
  onBounds: (value: string) => void;
}) {
  const map = useMap();
  useEffect(() => {
    if (selected)
      map.flyTo(
        [selected.latitude, selected.longitude],
        Math.max(map.getZoom(), 15),
        {
          animate: !window.matchMedia("(prefers-reduced-motion: reduce)")
            .matches,
        },
      );
  }, [selected?.id, map]);
  useEffect(() => {
    map.invalidateSize();
  }, [map]);
  useMapEvents({
    moveend: () => {
      const b = map.getBounds();
      onBounds(
        [b.getWest(), b.getSouth(), b.getEast(), b.getNorth()].join(","),
      );
    },
  });
  return (
    <button
      className="map-fit"
      title="Fit visible defects"
      aria-label="Fit visible defects"
      onClick={() => {
        if (items.length)
          map.fitBounds(
            items.map((d) => [d.latitude, d.longitude]),
            { padding: [35, 35], maxZoom: 15 },
          );
        else map.setView([12.981, 77.604], 14);
      }}
    >
      <Crosshair size={18} />
    </button>
  );
}

export default function RoadMap({
  items,
  selected,
  onSelect,
  onBounds,
}: {
  items: Defect[];
  selected: Defect | null;
  onSelect: (d: Defect) => void;
  onBounds: (value: string) => void;
}) {
  const [tileError, setTileError] = useState(false);
  return (
    <div className="map-wrap" aria-label="Interactive map of camera locations">
      <MapContainer
        center={[12.981, 77.604]}
        zoom={14}
        scrollWheelZoom
        className="road-map"
      >
        <TileLayer
          url="https://tile.openstreetmap.org/{z}/{x}/{y}.png"
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
          eventHandlers={{ tileerror: () => setTileError(true) }}
        />
        {items.map((d) => (
          <CircleMarker
            key={d.id}
            center={[d.latitude, d.longitude]}
            radius={selected?.id === d.id ? 10 : 7}
            pathOptions={{
              className: `defect-marker ${d.severity >= 65 ? "high" : d.severity >= 40 ? "medium" : "low"}`,
              fillOpacity: 0.95,
              weight: selected?.id === d.id ? 3 : 2,
            }}
            eventHandlers={{ click: () => onSelect(d) }}
          >
            <Tooltip>
              {label(d.defect_class)} · {d.severity.toFixed(0)} / 100
              <br />
              {d.road_name}
              {d.synthetic ? " · synthetic" : ""}
            </Tooltip>
          </CircleMarker>
        ))}
        <Controls selected={selected} items={items} onBounds={onBounds} />
      </MapContainer>
      <div className="map-location">
        <span className="live-dot" /> Camera locations <span>WGS84</span>
      </div>
      <div className="map-legend">
        <span>
          <i className="dot high" />
          High ≥65
        </span>
        <span>
          <i className="dot medium" />
          Moderate 40–64
        </span>
        <span>
          <i className="dot low" />
          Low &lt;40
        </span>
      </div>
      {tileError && (
        <div className="tile-warning" role="status">
          Basemap unavailable. Markers and the defect register remain usable.
        </div>
      )}
    </div>
  );
}
