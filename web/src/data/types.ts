// The shape of one run, as web/build_data.py writes it. Times are seconds from the run's start.

export type Role = "director" | "library" | "team-a" | "team-b" | "team-c" | "referee" | "solo" | "head" | "other";

export type Session = {
  phase: string;
  study: string | null;
  start: number;
  end: number | null;
  ok?: boolean;
  seconds?: number;
  cost?: number;
  error?: string | null;
};

export type AgentRec = {
  id: string;
  role: Role;
  study: string | null;
  model: string | null;
  sessions: Session[];
  cost: number;
  /** A rotation agent's name, what it can read and its portrait, as the backend's agent list sends them. */
  name?: string;
  /** The backend's job title for the agent ("Lab head", "Examiner", ...). */
  title?: string;
  reads?: string;
  portrait?: string | null;
};

export type Ev = {
  t: number;
  k: string;
  a?: string;
  s?: string | null;
  phase?: string;
  ok?: boolean;
  f?: string;
  to?: string;
  q?: string;
  items?: number;
  teams?: string[];
  round?: string;
  passed?: boolean;
  team?: string;
  valid?: boolean;
  between?: string[];
  fields?: Record<string, boolean>;
  agree?: boolean;
  mapping?: Record<string, string>;
  pick?: string;
  picked?: string | null;
  status?: string;
  final?: string;
  attempt?: number;
  n?: number;
  totals?: Totals;
  why?: string;
  // head.review (D-23)
  of?: string;
  approve?: boolean | null;
  notes?: number;
  delivered?: number;
  weak?: number;
  missing?: number;
  // relay.leak_check on a head's note: the department that wrote it
  by?: string;
};

export type Note = {
  id: string;
  t: number;
  kind: "note" | "pass_down";
  by: string;
  dept: string;
  label?: string;
  text: string;
  to?: string;
  reason?: string;
  came_from?: string[];
};

export type Search = {
  t: number;
  a: string;
  s: string | null;
  endpoint: string;
  q: string;
  urls?: string[] | null;
  results: { title: string; url: string; published: string }[];
};

export type Candidate = {
  agent: string;
  team: string;
  round: string;
  valid: boolean;
  answer: Record<string, unknown> | null;
};

export type Study = {
  id: string;
  title: string;
  status: string | null;
  final: string | null;
  final_round: string | null;
  briefed: string[] | null;
  candidates: Candidate[];
  comparisons: { round: string; between: string[]; fields: Record<string, boolean>; agree: boolean }[];
  questions: { to: string; q: string }[];
  challenge: null | {
    shared_assumptions?: string[];
    unused_evidence?: string[];
    unresolved_weak_points?: string[];
    second_readings?: string[];
    verdict?: string;
    questions?: { to: string; question: string }[];
  };
  challenge_changed_answer: boolean | null;
  referee: null | { difference?: string; test?: string; pick?: string; reason?: string };
  not_chosen: { agent: string; round: string; reason: string }[];
  heads?: Record<string, HeadReview>;
  grade: null | { lab: boolean | null; solo: (boolean | null)[]; vote: boolean | null };
};

/** One department head's review of a study (D-23), as build_data.clean_heads writes it. */
export type HeadReview = {
  ran?: boolean | null;
  verdict?: string | null;
  // the library head
  strong?: unknown[];
  weak?: unknown[];
  missing?: unknown[];
  // the team heads
  approve?: boolean | null;
  revised?: boolean | null;
  changed_answer?: boolean | null;
  notes?: { text: string | null; why: string | null; delivered: boolean | null; reasons: string[] }[];
};

export type Totals = {
  lab_passed: number;
  lab_studies: number;
  baseline_attempts_passed: number;
  baseline_attempts: number;
  vote_passed: number;
  vote_studies: number;
};

export type Run = {
  run: string;
  label: string;
  started: string;
  duration: number;
  lab_end: number | null;
  finished: boolean;
  config: {
    director_model?: string;
    worker_model?: string;
    timeouts?: Record<string, number>;
    max_searches?: number;
    brief_teams?: string[];
    challenge?: boolean;
    referee?: boolean;
    library?: boolean;
  };
  studies: Study[];
  agents: AgentRec[];
  events: Ev[];
  notes: Record<string, Note>;
  searches: Search[];
  totals: Totals | null;
};

export type RunIndexItem = {
  run: string;
  label: string;
  started: string;
  studies: number;
  agents: number;
  finished: boolean;
  source?: string;
  live?: boolean;
};
