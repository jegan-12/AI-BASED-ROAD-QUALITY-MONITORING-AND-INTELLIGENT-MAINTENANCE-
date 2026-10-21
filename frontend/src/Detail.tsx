import { useEffect, useState } from "react";
import { X, MapPin, Camera, GitMerge, Save } from "lucide-react";
import { blob, request } from "./api";
import { Defect, User, label } from "./types";

export default function Detail({
  id,
  user,
  onClose,
  onChanged,
}: {
  id: string;
  user: User;
  onClose: () => void;
  onChanged: () => void;
}) {
  const [item, setItem] = useState<Defect | null>(null),
    [image, setImage] = useState(""),
    [imageError, setImageError] = useState(""),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false),
    [success, setSuccess] = useState("");
  const [status, setStatus] = useState("new"),
    [critical, setCritical] = useState(false),
    [note, setNote] = useState(""),
    [reason, setReason] = useState("");
  const editable = user.role !== "viewer";
  useEffect(() => {
    let live = true;
    setItem(null);
    setError("");
    setSuccess("");
    request<Defect>("/defects/" + id)
      .then((d) => {
        if (live) {
          setItem(d);
          setStatus(d.status);
          setCritical(d.critical_location);
          setNote(d.note);
        }
      })
      .catch((e) => live && setError(e.message));
    return () => {
      live = false;
    };
  }, [id]);
  useEffect(() => {
    let live = true,
      url = "";
    setImage("");
    setImageError("");
    const observation = item?.observations?.[0];
    if (observation) {
      blob("/observations/" + observation.id + "/image")
        .then((b) => {
          url = URL.createObjectURL(b);
          if (live) setImage(url);
          else URL.revokeObjectURL(url);
        })
        .catch((e) => live && setImageError(e.message));
    }
    return () => {
      live = false;
      if (url) URL.revokeObjectURL(url);
    };
  }, [item?.id]);
  async function save() {
    if (!item) return;
    setBusy(true);
    setError("");
    try {
      const next = await request<Defect>("/defects/" + id, {
        method: "PATCH",
        body: JSON.stringify({
          status,
          note,
          critical_location: critical,
          revision: item.revision,
        }),
      });
      setItem({ ...next, observations: item.observations });
      setSuccess("Review saved to audit history.");
      onChanged();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function merge() {
    if (!item) return;
    setBusy(true);
    setError("");
    try {
      await request("/defects/" + id + "/merge", {
        method: "POST",
        body: JSON.stringify({
          target_id: item.duplicate_candidate_id,
          revision: item.revision,
          reason,
        }),
      });
      onChanged();
      onClose();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <aside className="detail panel" aria-label="Defect inspection">
      <div className="panel-title">
        <h2>Inspection record</h2>
        <button
          className="icon-button"
          onClick={onClose}
          aria-label="Close inspection"
        >
          <X size={19} />
        </button>
      </div>
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      {!item ? (
        <p className="muted">Loading inspection…</p>
      ) : (
        <>
          <div className="record-heading">
            <span className={"badge " + (item.synthetic ? "demo" : "")}>
              {item.synthetic ? "Synthetic" : "Model detection"}
            </span>
            <span className="record-id">{item.id.slice(0, 8)}</span>
          </div>
          <h3>{label(item.defect_class)}</h3>
          <p className="muted">
            <MapPin size={14} /> {item.road_name}
          </p>
          {image ? (
            <div className="evidence">
              <img src={image} alt="Original road survey frame" />
              <svg
                viewBox="0 0 100 100"
                preserveAspectRatio="none"
                aria-label="Detected bounding box"
              >
                <rect
                  x={item.bbox[0] * 100}
                  y={item.bbox[1] * 100}
                  width={(item.bbox[2] - item.bbox[0]) * 100}
                  height={(item.bbox[3] - item.bbox[1]) * 100}
                />
              </svg>
            </div>
          ) : (
            <div className="evidence-empty">
              <Camera size={28} />
              <p>{imageError || "Loading source image…"}</p>
            </div>
          )}
          <div className="score-pair">
            <div>
              <small>VISUAL SEVERITY</small>
              <strong>
                {item.severity.toFixed(0)}
                <em>/100</em>
              </strong>
              <span>
                {item.explanation.calibration_version
                  ? "Calibrated to expert ratings"
                  : "Uncalibrated screening score"}
              </span>
            </div>
            <div>
              <small>CONFIDENCE</small>
              <strong>
                {Math.round(item.confidence * 100)}
                <em>%</em>
              </strong>
              <span>Detector confidence</span>
            </div>
          </div>
          <details>
            <summary>How this score was calculated</summary>
            <p>
              Class base {item.explanation.class_base} + image area
              contribution. Image area proxy:{" "}
              {(item.explanation.image_area_ratio * 100).toFixed(2)}%. Raw
              score: {item.explanation.raw_score}.
            </p>
            <p>
              {item.explanation.measurement}. Confidence does not affect
              severity.{" "}
              {item.explanation.calibration_version ||
                "No field calibration supplied."}
            </p>
            <p>
              Priority {item.priority}:{" "}
              {Object.entries(item.priority_reasons)
                .map(([k, v]) => `${label(k)} ${v}`)
                .join(" + ")}
              .
            </p>
          </details>
          <dl className="record-facts">
            <div>
              <dt>Camera position</dt>
              <dd>
                {item.latitude.toFixed(5)}, {item.longitude.toFixed(5)}
              </dd>
            </div>
            <div>
              <dt>GPS uncertainty</dt>
              <dd>±{item.gps_uncertainty_m.toFixed(1)} m</dd>
            </div>
            <div>
              <dt>Captured</dt>
              <dd>{new Date(item.captured_at).toLocaleString()}</dd>
            </div>
            <div>
              <dt>Model</dt>
              <dd>{item.model_version}</dd>
            </div>
            <div>
              <dt>Observations</dt>
              <dd>{item.observations?.length || 0}</dd>
            </div>
          </dl>
          {editable ? (
            <form
              onSubmit={(e) => {
                e.preventDefault();
                save();
              }}
              className="review-form"
            >
              <label>
                Review status
                <select
                  value={status}
                  onChange={(e) => setStatus(e.target.value)}
                >
                  {[
                    "new",
                    "confirmed",
                    "scheduled",
                    "repaired",
                    "rejected",
                  ].map((s) => (
                    <option key={s}>{s}</option>
                  ))}
                </select>
              </label>
              <label className="checkbox">
                <input
                  type="checkbox"
                  checked={critical}
                  onChange={(e) => setCritical(e.target.checked)}
                />
                Critical location
              </label>
              <label>
                Inspection note
                <textarea
                  value={note}
                  onChange={(e) => setNote(e.target.value)}
                  maxLength={2000}
                />
              </label>
              <button className="primary" disabled={busy}>
                <Save size={16} />
                {busy ? "Saving…" : "Save review"}
              </button>
            </form>
          ) : (
            <p className="muted">
              Viewer access. An inspector can update this record.
            </p>
          )}
          {success && (
            <p className="success" role="status">
              {success}
            </p>
          )}
          {item.duplicate_candidate_id && editable && (
            <div className="duplicate">
              <h4>
                <GitMerge size={16} />
                Possible duplicate
              </h4>
              <p>
                Compare with record {item.duplicate_candidate_id.slice(0, 8)}.
                Nearby camera positions do not prove the same defect.
              </p>
              <button
                onClick={() =>
                  window.dispatchEvent(
                    new CustomEvent("open-defect", {
                      detail: item.duplicate_candidate_id,
                    }),
                  )
                }
              >
                Inspect candidate
              </button>
              <label>
                Merge reason
                <input
                  value={reason}
                  onChange={(e) => setReason(e.target.value)}
                  minLength={5}
                  maxLength={1000}
                />
              </label>
              <button disabled={busy || reason.length < 5} onClick={merge}>
                Merge into candidate
              </button>
            </div>
          )}
        </>
      )}
    </aside>
  );
}
