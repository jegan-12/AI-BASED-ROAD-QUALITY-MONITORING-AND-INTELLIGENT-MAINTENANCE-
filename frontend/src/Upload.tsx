import { FormEvent, useState } from "react";
import { UploadCloud } from "lucide-react";
import { request } from "./api";
import type { Job } from "./types";
export default function Upload({ onQueued }: { onQueued: () => void }) {
  const [file, setFile] = useState<File | null>(null),
    [track, setTrack] = useState<File | null>(null),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false),
    [success, setSuccess] = useState("");
  const video = !!file && /\.(mp4|mov|avi)$/i.test(file.name);
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setSuccess("");
    if (!file) return;
    setBusy(true);
    try {
      const fields = new FormData(event.currentTarget);
      const meta = {
        captured_at: new Date(String(fields.get("captured"))).toISOString(),
        road_name: fields.get("road"),
        ...(video
          ? { gps_track: JSON.parse(await track!.text()) }
          : {
              latitude: Number(fields.get("lat")),
              longitude: Number(fields.get("lon")),
              gps_uncertainty_m: Number(fields.get("uncertainty")),
            }),
      };
      const data = new FormData();
      data.set("file", file);
      data.set("metadata", JSON.stringify(meta));
      const job = await request<Job>("/jobs", {
        method: "POST",
        headers: { "Idempotency-Key": crypto.randomUUID() },
        body: data,
      });
      setSuccess("Survey queued: " + job.id.slice(0, 8));
      onQueued();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="panel upload-panel">
      <div className="panel-title">
        <div>
          <span className="eyebrow">NEW SURVEY</span>
          <h2>Bring the road into view</h2>
        </div>
        <UploadCloud size={26} />
      </div>
      <p className="muted">
        Upload an image or a video up to 100 MB. Coordinates represent the
        camera position. Videos require a timestamped GPS track.
      </p>
      <form onSubmit={submit}>
        <label className="file-drop">
          <UploadCloud size={32} />
          <strong>{file?.name || "Choose a road image or video"}</strong>
          <span>JPEG, PNG, WebP · MP4, MOV, AVI</span>
          <input
            required
            type="file"
            accept=".jpg,.jpeg,.png,.webp,.mp4,.mov,.avi"
            onChange={(e) => setFile(e.target.files?.[0] || null)}
          />
        </label>
        <div className="form-grid">
          <label>
            Road or survey name
            <input
              name="road"
              required
              maxLength={120}
              placeholder="MG Road · eastbound"
            />
          </label>
          <label>
            Capture time (local)
            <input name="captured" type="datetime-local" required />
          </label>
        </div>
        {video ? (
          <label>
            GPS track JSON
            <input
              type="file"
              required
              accept=".json"
              onChange={(e) => setTrack(e.target.files?.[0] || null)}
            />
            <small>
              Array of offset_seconds, latitude, longitude, uncertainty_m. Start
              at 0; gaps ≤10 seconds.
            </small>
          </label>
        ) : (
          <div className="form-grid triple">
            <label>
              Latitude
              <input
                name="lat"
                type="number"
                step="any"
                min="-90"
                max="90"
                required
              />
            </label>
            <label>
              Longitude
              <input
                name="lon"
                type="number"
                step="any"
                min="-180"
                max="180"
                required
              />
            </label>
            <label>
              GPS uncertainty (m)
              <input
                name="uncertainty"
                type="number"
                step="any"
                min="0"
                max="10000"
                required
              />
            </label>
          </div>
        )}
        {error && (
          <p role="alert" className="error">
            {error}
          </p>
        )}
        {success && (
          <p role="status" className="success">
            {success}
          </p>
        )}
        <button className="primary" disabled={busy}>
          {busy ? "Uploading…" : "Queue survey"}
          <UploadCloud size={16} />
        </button>
      </form>
    </section>
  );
}
