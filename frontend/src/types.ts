export type User = {
  id: string;
  username: string;
  role: "viewer" | "inspector" | "admin";
  enabled: boolean;
};
export type Defect = {
  id: string;
  job_id: string;
  defect_class: string;
  confidence: number;
  bbox: number[];
  latitude: number;
  longitude: number;
  gps_uncertainty_m: number;
  captured_at: string;
  severity: number;
  explanation: {
    raw_score: number;
    class_base: number;
    image_area_ratio: number;
    area_source: string;
    calibration_version: string | null;
    measurement: string;
  };
  model_version: string;
  synthetic: boolean;
  road_name: string;
  status: string;
  critical_location: boolean;
  note: string;
  revision: number;
  duplicate_candidate_id: string | null;
  merged_into_id: string | null;
  priority: number;
  priority_reasons: Record<string, number>;
  observations?: Observation[];
};
export type Observation = {
  id: string;
  job_id: string;
  frame_index: number;
  captured_at: string;
  details: { bbox: number[]; association?: string; synthetic: boolean };
};
export type Job = {
  id: string;
  kind: string;
  status: string;
  progress: number;
  attempts: number;
  error: string | null;
  created_at: string;
  inference_ms: number | null;
  model_info: { version: string; synthetic: boolean } | null;
  road_name: string;
};
export type Analytics = {
  total: number;
  active: number;
  synthetic: number;
  high_severity: number;
  observed_health: number | null;
  health_method: string;
  by_class: Record<string, number>;
  by_status: Record<string, number>;
  by_day: Record<string, number>;
  priorities: Defect[];
};
export const classes = [
  "pothole",
  "longitudinal_crack",
  "transverse_crack",
  "alligator_cracking",
  "rutting",
  "other",
];
export const label = (text: string) =>
  text.replaceAll("_", " ").replace(/^./, (x) => x.toUpperCase());
