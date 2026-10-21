import React, { FormEvent, useCallback, useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  Activity,
  ArrowDownToLine,
  ArrowRight,
  BarChart3,
  ChevronRight,
  ClipboardList,
  Filter,
  Layers,
  LogOut,
  Map,
  Menu,
  Plus,
  RefreshCw,
  Route,
  Search,
  ShieldCheck,
  UploadCloud,
  X,
} from "lucide-react";
import RoadMap from "./Map";
import Detail from "./Detail";
import Upload from "./Upload";
import { exportCSV, hasToken, request, setToken } from "./api";
import { Analytics, Defect, Job, User, classes, label } from "./types";
import "./styles.css";

function Login({ onLogin }: { onLogin: (user: User) => void }) {
  const [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setBusy(true);
    setError("");
    const data = new FormData(e.currentTarget);
    try {
      const result = await request<{ access_token: string; user: User }>(
        "/auth/token",
        {
          method: "POST",
          body: new URLSearchParams({
            username: String(data.get("username")),
            password: String(data.get("password")),
          }),
        },
      );
      setToken(result.access_token);
      onLogin(result.user);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <main className="login">
      <div className="login-story">
        <div className="wordmark">
          <Route />
          road<span>scope</span>
        </div>
        <span className="eyebrow">
          ROAD INTELLIGENCE / MAINTENANCE OPERATIONS
        </span>
        <h1>
          Better roads start
          <br />
          with a clearer view.
        </h1>
        <p>
          A shared workspace to inspect road defects, understand their context,
          and decide what needs attention next.
        </p>
        <div className="login-diagram">
          <span>01 Capture</span>
          <ChevronRight />
          <span>02 Inspect</span>
          <ChevronRight />
          <span>03 Maintain</span>
        </div>
        <small>
          Visual screening supports engineering judgement. It does not replace a
          field survey.
        </small>
      </div>
      <section className="login-form panel">
        <span className="eyebrow">YOUR OPERATIONS WORKSPACE</span>
        <h2>Sign in to RoadScope</h2>
        <p className="muted">Use the account created by your administrator.</p>
        <form onSubmit={submit}>
          <label>
            Username
            <input name="username" autoComplete="username" required autoFocus />
          </label>
          <label>
            Password
            <input
              name="password"
              type="password"
              autoComplete="current-password"
              required
              maxLength={128}
            />
          </label>
          {error && (
            <p className="error" role="alert">
              {error}
            </p>
          )}
          <button className="primary" disabled={busy}>
            {busy ? "Signing in…" : "Open workspace"}
            <ArrowRight size={17} />
          </button>
        </form>
        <p className="login-help">
          First run? Create an administrator with the setup command in the
          repository README. There is no default password.
        </p>
      </section>
    </main>
  );
}

function Admin() {
  const [users, setUsers] = useState<User[]>([]),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  const load = () =>
    request<User[]>("/users")
      .then(setUsers)
      .catch((e) => setError(e.message));
  useEffect(() => {
    load();
  }, []);
  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = e.currentTarget,
      data = new FormData(form);
    setBusy(true);
    setError("");
    try {
      await request("/users", {
        method: "POST",
        body: JSON.stringify(Object.fromEntries(data)),
      });
      form.reset();
      load();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function toggle(u: User) {
    try {
      await request("/users/" + u.id, {
        method: "PATCH",
        body: JSON.stringify({ role: u.role, enabled: !u.enabled }),
      });
      load();
    } catch (e) {
      setError((e as Error).message);
    }
  }
  return (
    <section className="panel">
      <div className="panel-title">
        <h2>Organization access</h2>
        <ShieldCheck />
      </div>
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      <div className="user-list">
        {users.map((u) => (
          <div key={u.id}>
            <strong>{u.username}</strong>
            <span className="badge">{u.role}</span>
            <button onClick={() => toggle(u)}>
              {u.enabled ? "Disable" : "Enable"}
            </button>
          </div>
        ))}
      </div>
      <h3>Create an account</h3>
      <form onSubmit={submit}>
        <div className="form-grid">
          <label>
            Username
            <input
              name="username"
              required
              minLength={3}
              maxLength={80}
              pattern="[a-zA-Z0-9_.@\-]+"
            />
          </label>
          <label>
            Initial password
            <input
              type="password"
              name="password"
              required
              minLength={12}
              maxLength={128}
              autoComplete="new-password"
            />
          </label>
          <label>
            Role
            <select name="role">
              <option>viewer</option>
              <option>inspector</option>
              <option>admin</option>
            </select>
          </label>
        </div>
        <button className="primary" disabled={busy}>
          {busy ? "Creating…" : "Create account"}
        </button>
      </form>
    </section>
  );
}

function App() {
  const [user, setUser] = useState<User | null>(null),
    [boot, setBoot] = useState(hasToken()),
    [page, setPage] = useState("overview"),
    [menu, setMenu] = useState(false),
    [items, setItems] = useState<Defect[]>([]),
    [total, setTotal] = useState(0),
    [analytics, setAnalytics] = useState<Analytics | null>(null),
    [jobs, setJobs] = useState<Job[]>([]),
    [model, setModel] = useState<Record<string, unknown> | null>(null),
    [selected, setSelected] = useState<Defect | null>(null),
    [selectedId, setSelectedId] = useState(""),
    [error, setError] = useState(""),
    [loading, setLoading] = useState(false),
    [refresh, setRefresh] = useState(0),
    [demo, setDemo] = useState(false);
  const [cls, setCls] = useState(""),
    [status, setStatus] = useState(""),
    [source, setSource] = useState(""),
    [minimum, setMinimum] = useState("0"),
    [since, setSince] = useState(""),
    [until, setUntil] = useState(""),
    [search, setSearch] = useState(""),
    [bounds, setBounds] = useState(""),
    [appliedBounds, setAppliedBounds] = useState("");
  const params = new URLSearchParams();
  if (cls) params.set("defect_class", cls);
  if (status) params.set("status", status);
  if (source) params.set("synthetic", source);
  params.set("min_severity", minimum);
  if (since) params.set("since", since + "T00:00:00Z");
  if (until) params.set("until", until + "T23:59:59Z");
  if (appliedBounds) params.set("bbox", appliedBounds);
  const query = params.toString();
  const reload = useCallback(() => setRefresh((x) => x + 1), []);
  useEffect(() => {
    if (hasToken())
      request<User>("/auth/me")
        .then(setUser)
        .catch(() => setToken(""))
        .finally(() => setBoot(false));
    const expired = () => {
      setUser(null);
      setError("");
    };
    window.addEventListener("session-expired", expired);
    return () => window.removeEventListener("session-expired", expired);
  }, []);
  useEffect(() => {
    if (!user) return;
    let active = true;
    setLoading(true);
    setError("");
    Promise.all([
      request<{ items: Defect[]; total: number }>(
        "/defects?" + query + "&limit=2000",
      ),
      request<Analytics>("/analytics?" + query),
    ])
      .then(([d, a]) => {
        if (active) {
          setItems(d.items);
          setTotal(d.total);
          setAnalytics(a);
        }
      })
      .catch((e) => active && setError(e.message))
      .finally(() => active && setLoading(false));
    return () => {
      active = false;
    };
  }, [user, query, refresh]);
  useEffect(() => {
    if (!user) return;
    request<{ demo_mode: boolean }>("/health")
      .then((d) => setDemo(d.demo_mode))
      .catch(() => {});
    request<Record<string, unknown>>("/model")
      .then(setModel)
      .catch(() => {});
  }, [user, refresh]);
  useEffect(() => {
    if (!user || page !== "surveys") return;
    let live = true;
    const load = () =>
      request<Job[]>("/jobs")
        .then((j) => live && setJobs(j))
        .catch((e) => live && setError(e.message));
    load();
    const timer = setInterval(load, 4000);
    return () => {
      live = false;
      clearInterval(timer);
    };
  }, [user, page, refresh]);
  useEffect(() => {
    const open = (event: Event) =>
      setSelectedId((event as CustomEvent<string>).detail);
    window.addEventListener("open-defect", open);
    return () => window.removeEventListener("open-defect", open);
  }, []);
  const choose = (d: Defect) => {
    setSelected(d);
    setSelectedId(d.id);
  };
  const visible = items.filter((d) =>
    (d.road_name + " " + d.defect_class + " " + d.id)
      .toLowerCase()
      .includes(search.toLowerCase()),
  );
  async function logout() {
    try {
      await request("/auth/logout", { method: "POST" });
    } catch {}
    setToken("");
    setUser(null);
    setItems([]);
    setSelectedId("");
  }
  async function download() {
    try {
      await exportCSV(query);
    } catch (e) {
      setError((e as Error).message);
    }
  }
  if (boot) return <div className="boot">Opening RoadScope…</div>;
  if (!user) return <Login onLogin={setUser} />;
  const nav = [
    { id: "overview", name: "Road overview", icon: Map },
    { id: "register", name: "Defect register", icon: ClipboardList },
    { id: "surveys", name: "Surveys & uploads", icon: UploadCloud },
    { id: "analytics", name: "Analytics & reports", icon: BarChart3 },
    ...(user.role === "admin"
      ? [{ id: "admin", name: "Access control", icon: ShieldCheck }]
      : []),
  ];
  return (
    <div className="app-shell">
      <a href="#main" className="skip-link">
        Skip to content
      </a>
      <aside className={"sidebar " + (menu ? "open" : "")}>
        <a
          className="wordmark"
          href="#overview"
          onClick={() => setPage("overview")}
        >
          <Route />
          road<span>scope</span>
        </a>
        <div className="workspace">
          <span className="workspace-icon">R</span>
          <div>
            <strong>Road operations</strong>
            <small>Municipal workspace</small>
          </div>
        </div>
        <span className="nav-label">WORKSPACE</span>
        <nav>
          {nav.map(({ id, name, icon: Icon }) => (
            <button
              key={id}
              className={page === id ? "active" : ""}
              onClick={() => {
                setPage(id);
                setMenu(false);
              }}
            >
              <Icon size={19} />
              {name}
              {page === id && <ChevronRight size={14} />}
            </button>
          ))}
        </nav>
        <div className="sidebar-note">
          <Activity size={20} />
          <strong>Evidence before action.</strong>
          <p>
            Review AI detections and location uncertainty before scheduling
            maintenance.
          </p>
        </div>
        <div className="profile">
          <span>{user.username.slice(0, 2).toUpperCase()}</span>
          <div>
            <strong>{user.username}</strong>
            <small>{label(user.role)}</small>
          </div>
          <button
            className="icon-button"
            onClick={logout}
            aria-label="Sign out"
          >
            <LogOut size={17} />
          </button>
        </div>
      </aside>
      <div className="app-body">
        <header className="topbar">
          <button
            className="mobile-menu icon-button"
            aria-label="Toggle navigation"
            onClick={() => setMenu(!menu)}
          >
            {menu ? <X /> : <Menu />}
          </button>
          <div className="breadcrumb">
            Workspace <ChevronRight size={13} />
            <strong>{nav.find((n) => n.id === page)?.name}</strong>
          </div>
          <span className="top-status">
            <span className="live-dot" />
            {demo ? "Demo environment" : "Organization workspace"}
          </span>
        </header>
        <main id="main">
          <div className="page-heading">
            <div>
              <span className="eyebrow">OBSERVE. UNDERSTAND. MAINTAIN.</span>
              <h1>
                {page === "overview"
                  ? "A clearer view of your roads."
                  : page === "register"
                    ? "Every defect. One register."
                    : page === "surveys"
                      ? "From survey to evidence."
                      : page === "analytics"
                        ? "Turn observations into priorities."
                        : "The right access, for every role."}
              </h1>
              <p>
                {page === "overview"
                  ? "Explore detected defects and focus maintenance where it matters."
                  : page === "surveys"
                    ? "Trace each upload from the processing queue to its inspection records."
                    : "A shared, traceable view of your road maintenance operations."}
              </p>
            </div>
            <div className="heading-actions">
              <button
                onClick={reload}
                aria-label="Refresh data"
                disabled={loading}
              >
                <RefreshCw size={16} />
              </button>
              <button onClick={download}>
                <ArrowDownToLine size={16} />
                Export CSV
              </button>
              {user.role !== "viewer" && (
                <button className="primary" onClick={() => setPage("surveys")}>
                  <Plus size={17} />
                  New survey
                </button>
              )}
            </div>
          </div>
          {demo && (
            <div className="demo-banner">
              <span className="badge demo">DEMO DATA</span>
              <span>
                Synthetic examples are labeled throughout. Scores are visual
                screening estimates, not physical measurements.
              </span>
            </div>
          )}
          {error && (
            <div className="error" role="alert">
              {error}
              <button onClick={reload}>Retry</button>
            </div>
          )}
          {["overview", "register", "analytics"].includes(page) && (
            <>
              <section className="metrics" aria-label="Filtered survey metrics">
                <div>
                  <span>Observed defects</span>
                  <strong>{analytics?.total ?? "—"}</strong>
                  <small>
                    <Layers size={13} />
                    {analytics
                      ? `${analytics.synthetic} synthetic records`
                      : "Loading records"}
                  </small>
                </div>
                <div>
                  <span>Awaiting maintenance</span>
                  <strong>{analytics?.active ?? "—"}</strong>
                  <small>New, confirmed & scheduled</small>
                </div>
                <div>
                  <span>High severity</span>
                  <strong className="danger-text">
                    {analytics?.high_severity ?? "—"}
                  </strong>
                  <small>Screening score ≥65 / 100</small>
                </div>
                <div>
                  <span>Observed health indicator</span>
                  <strong>
                    {analytics?.observed_health ?? "—"}
                    <em>/100</em>
                  </strong>
                  <small>Observed defects only · not PCI</small>
                </div>
              </section>
              <section className="filters" aria-label="Filter defects">
                <label className="search-field">
                  <span>Search loaded records</span>
                  <div>
                    <Search size={17} />
                    <input
                      value={search}
                      onChange={(e) => setSearch(e.target.value)}
                      placeholder="Road, defect or record ID"
                    />
                  </div>
                </label>
                <label>
                  Defect type
                  <select value={cls} onChange={(e) => setCls(e.target.value)}>
                    <option value="">All defect types</option>
                    {classes.map((c) => (
                      <option value={c} key={c}>
                        {label(c)}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  Status
                  <select
                    value={status}
                    onChange={(e) => setStatus(e.target.value)}
                  >
                    <option value="">All statuses</option>
                    {[
                      "new",
                      "confirmed",
                      "scheduled",
                      "repaired",
                      "rejected",
                    ].map((s) => (
                      <option value={s} key={s}>
                        {label(s)}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  Data source
                  <select
                    value={source}
                    onChange={(e) => setSource(e.target.value)}
                  >
                    <option value="">All sources</option>
                    <option value="false">Real observations</option>
                    <option value="true">Synthetic demo</option>
                  </select>
                </label>
                <label>
                  Min. severity
                  <select
                    value={minimum}
                    onChange={(e) => setMinimum(e.target.value)}
                  >
                    <option value="0">All scores</option>
                    <option value="40">40 and above</option>
                    <option value="65">65 and above</option>
                  </select>
                </label>
                <details className="more-filters">
                  <summary>
                    <Filter size={15} />
                    Dates
                  </summary>
                  <div>
                    <label>
                      From (UTC)
                      <input
                        type="date"
                        value={since}
                        onChange={(e) => setSince(e.target.value)}
                      />
                    </label>
                    <label>
                      Through (UTC)
                      <input
                        type="date"
                        value={until}
                        onChange={(e) => setUntil(e.target.value)}
                      />
                    </label>
                  </div>
                </details>
              </section>
            </>
          )}
          {loading && (
            <div className="loading-line" role="status">
              Updating observations…
            </div>
          )}
          {page === "overview" && (
            <div className={"map-layout " + (selectedId ? "inspecting" : "")}>
              <section className="map-panel panel">
                <div className="panel-title">
                  <div>
                    <h2>Road condition map</h2>
                    <small>
                      {visible.length} displayed / {total} filtered records
                    </small>
                  </div>
                  <button
                    onClick={() =>
                      setAppliedBounds(appliedBounds ? "" : bounds)
                    }
                    disabled={!bounds && !appliedBounds}
                  >
                    {appliedBounds ? "Clear area" : "Filter this area"}
                  </button>
                </div>
                <RoadMap
                  items={visible}
                  selected={selected}
                  onSelect={choose}
                  onBounds={setBounds}
                />
                <div className="map-caption">
                  <Map size={14} />
                  <span>
                    Markers show camera GPS positions. Select a marker or record
                    to inspect evidence.
                  </span>
                </div>
              </section>
              {selectedId ? (
                <Detail
                  id={selectedId}
                  user={user}
                  onClose={() => {
                    setSelectedId("");
                    setSelected(null);
                  }}
                  onChanged={reload}
                />
              ) : (
                <section className="panel priority-panel">
                  <div className="panel-title">
                    <div>
                      <span className="eyebrow">MAINTENANCE QUEUE</span>
                      <h2>Needs attention</h2>
                    </div>
                    <span className="count">{analytics?.active ?? 0}</span>
                  </div>
                  <p className="muted">
                    Ranked by severity, observation age, and critical location.
                  </p>
                  {analytics?.priorities.slice(0, 5).map((d, i) => (
                    <button
                      key={d.id}
                      className="priority-item"
                      onClick={() => choose(d)}
                    >
                      <span className="rank">0{i + 1}</span>
                      <div>
                        <strong>{d.road_name}</strong>
                        <span>
                          {label(d.defect_class)}
                          {d.synthetic ? " · demo" : ""}
                        </span>
                      </div>
                      <span
                        className={
                          "severity " + (d.severity >= 65 ? "high" : "medium")
                        }
                      >
                        {d.priority.toFixed(0)}
                      </span>
                      <ChevronRight size={15} />
                    </button>
                  ))}
                  {!analytics?.priorities.length && (
                    <p className="empty">
                      No active records in this selection. Upload a survey or
                      adjust the filters.
                    </p>
                  )}
                  <button
                    className="text-button"
                    onClick={() => setPage("register")}
                  >
                    Open defect register <ArrowRight size={16} />
                  </button>
                  <div className="method-note">
                    <ShieldCheck size={18} />
                    <p>
                      Priority is a policy score. Field verification is required
                      before intervention.
                    </p>
                  </div>
                </section>
              )}
            </div>
          )}
          {["overview", "register"].includes(page) && (
            <section className="panel register">
              <div className="panel-title">
                <div>
                  <h2>
                    {page === "overview"
                      ? "Recent observations"
                      : "Defect register"}
                  </h2>
                  <small>
                    {total > 2000
                      ? "Showing the first 2,000 records. Narrow filters or export all filtered records."
                      : "Select a record to view evidence and review its status."}
                  </small>
                </div>
                <span className="count">{visible.length}</span>
              </div>
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>Road / record</th>
                      <th>Defect</th>
                      <th>Severity</th>
                      <th>Confidence</th>
                      <th>Status</th>
                      <th>Captured</th>
                      <th>Source</th>
                      <th>
                        <span className="sr-only">Inspect</span>
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {visible
                      .slice(0, page === "overview" ? 5 : 2000)
                      .map((d) => (
                        <tr key={d.id}>
                          <td data-label="Road">
                            <button
                              className="record-link"
                              onClick={() => {
                                choose(d);
                                if (page === "register") setPage("overview");
                              }}
                            >
                              {d.road_name}
                              <small>{d.id.slice(0, 8)}</small>
                            </button>
                          </td>
                          <td data-label="Defect">{label(d.defect_class)}</td>
                          <td data-label="Severity">
                            <span
                              className={
                                "severity " +
                                (d.severity >= 65
                                  ? "high"
                                  : d.severity >= 40
                                    ? "medium"
                                    : "low")
                              }
                            >
                              {d.severity.toFixed(0)}
                            </span>
                          </td>
                          <td data-label="Confidence">
                            {Math.round(d.confidence * 100)}%
                          </td>
                          <td data-label="Status">
                            <span className={"badge status-" + d.status}>
                              {label(d.status)}
                            </span>
                          </td>
                          <td data-label="Captured">
                            {new Date(d.captured_at).toLocaleDateString(
                              undefined,
                              { month: "short", day: "numeric" },
                            )}
                          </td>
                          <td data-label="Source">
                            <span className={d.synthetic ? "demo-text" : ""}>
                              {d.synthetic ? "Synthetic" : "Model"}
                            </span>
                          </td>
                          <td>
                            <button
                              className="icon-button"
                              aria-label={"Inspect " + d.id}
                              onClick={() => {
                                choose(d);
                                setPage("overview");
                              }}
                            >
                              <ChevronRight size={16} />
                            </button>
                          </td>
                        </tr>
                      ))}
                  </tbody>
                </table>
                {!visible.length && (
                  <div className="empty">
                    <Search size={24} />
                    <p>No defects match these filters.</p>
                    <button
                      onClick={() => {
                        setCls("");
                        setStatus("");
                        setSource("");
                        setMinimum("0");
                        setSearch("");
                        setSince("");
                        setUntil("");
                        setAppliedBounds("");
                      }}
                    >
                      Clear filters
                    </button>
                  </div>
                )}
              </div>
            </section>
          )}
          {page === "surveys" && (
            <div className="surveys-layout">
              {user.role !== "viewer" && <Upload onQueued={reload} />}
              <section className="panel">
                <div className="panel-title">
                  <h2>Processing queue</h2>
                  <span className="count">{jobs.length}</span>
                </div>
                <p className="muted">
                  Updates every 4 seconds. Up to 150 sampled frames per video;
                  three attempts for transient service failures.
                </p>
                {jobs.map((j) => (
                  <div className="job-item" key={j.id}>
                    <div>
                      <strong>{j.road_name}</strong>
                      <span>
                        {j.id.slice(0, 8)} · {j.kind} · attempt {j.attempts}
                      </span>
                    </div>
                    <span className={"badge status-" + j.status}>
                      {j.status}
                    </span>
                    <progress
                      value={j.progress}
                      max={100}
                      aria-label="Processing progress"
                    />
                    {j.error && <p className="error">{j.error}</p>}
                    {j.model_info && (
                      <small>
                        {j.model_info.synthetic ? "Synthetic fixture · " : ""}
                        {j.model_info.version}
                        {j.inference_ms != null
                          ? ` · ${(j.inference_ms / 1000).toFixed(2)} s total inference`
                          : ""}
                      </small>
                    )}
                    {j.status === "failed" && user.role !== "viewer" && (
                      <button
                        onClick={() =>
                          request("/jobs/" + j.id + "/retry", {
                            method: "POST",
                          })
                            .then(reload)
                            .catch((e) => setError(e.message))
                        }
                      >
                        Retry job
                      </button>
                    )}
                  </div>
                ))}
                {!jobs.length && (
                  <p className="empty">
                    No surveys yet. Queue an upload to begin.
                  </p>
                )}
              </section>
            </div>
          )}
          {page === "analytics" && analytics && (
            <div className="analytics-grid">
              <section className="panel">
                <div className="panel-title">
                  <h2>Defect distribution</h2>
                  <BarChart3 />
                </div>
                <p className="muted">
                  Counts within the current filters. Unequal survey coverage
                  affects comparisons.
                </p>
                {Object.entries(analytics.by_class).map(([c, n]) => (
                  <div className="bar-row" key={c}>
                    <div>
                      <span>{label(c)}</span>
                      <strong>{n}</strong>
                    </div>
                    <meter
                      min={0}
                      max={Math.max(1, analytics.total)}
                      value={n}
                    />
                  </div>
                ))}
              </section>
              <section className="panel">
                <h2>Observation timeline</h2>
                <p className="muted">
                  Capture dates, not changes in road condition.
                </p>
                <div className="timeline">
                  {Object.entries(analytics.by_day).map(([date, n]) => (
                    <div key={date}>
                      <span>{date.slice(5)}</span>
                      <meter
                        min={0}
                        max={Math.max(1, ...Object.values(analytics.by_day))}
                        value={n}
                      />
                      <strong>{n}</strong>
                    </div>
                  ))}
                </div>
              </section>
              <section className="panel">
                <h2>Explainable health indicator</h2>
                <p>{analytics.health_method}.</p>
                <p className="muted">
                  This describes observed defects. Survey distance, defect-free
                  pavement, traffic exposure, and network coverage are unknown.
                  A missing score means insufficient active observations.
                </p>
                <button onClick={download}>
                  <ArrowDownToLine size={16} />
                  Export filtered report
                </button>
              </section>
              <section className="panel">
                <h2>Model registry</h2>
                <span className="badge">
                  {String(model?.status || "unavailable")}
                </span>
                <p>
                  Version: {String(model?.version || "No model registered")}
                </p>
                {model?.metrics ? (
                  <pre className="model-metrics">
                    {JSON.stringify(model.metrics, null, 2)}
                  </pre>
                ) : (
                  <p className="muted">
                    No measured model accuracy is available. Register a
                    road-specific model with a held-out evaluation to populate
                    precision, recall, and mAP.
                  </p>
                )}
                <details>
                  <summary>Model provenance and limitations</summary>
                  <pre className="model-metrics">
                    {JSON.stringify(model, null, 2)}
                  </pre>
                </details>
              </section>
            </div>
          )}
          {page === "admin" && user.role === "admin" && <Admin />}
          <footer>
            <span>
              RoadScope <span className="muted">/ Road intelligence</span>
            </span>
            <span>Camera GPS · Visual screening · Human review</span>
          </footer>
        </main>
      </div>
    </div>
  );
}

createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
