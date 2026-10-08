export type Action = 'snapshot' | 'network' | 'logs' | 'google' | 'trust' | 'quality' | 'patrol' | 'update_data'
export type TaskStatus = 'queued' | 'running' | 'succeeded' | 'failed' | 'cancelled'
export interface Policy { google: boolean; trust: boolean; interval_minutes: number; scheduled_action: Action; region_path: string }
export interface Metrics {
  public_ip?: string | null; country?: string | null; youtube_region?: string | null;
  load_1m?: number; disk_used_percent?: number; memory_used_percent?: number | null;
  cpu_count?: number; memory_total_mb?: number | null; policy_error?: string;
}
export interface SentinelNode {
  id: string; name: string; hostname: string; platform: string; region: string; group_name: string;
  version: string; online: boolean; seen: number; created: number; metrics: Metrics;
  policy: Policy; capabilities: Action[];
}
export interface Task {
  id: string; node_id: string; node_name: string; action: Action; status: TaskStatus;
  created: number; started: number | null; finished: number | null; source: string;
  cancel_requested: number; result?: Record<string, unknown> | null;
}
export interface AuditEvent { id: number; created: number; kind: string; node_id: string | null; message: string }
export interface Overview {
  nodes: SentinelNode[]; jobs: Task[]; events: AuditEvent[]; counts: Partial<Record<TaskStatus, number>>;
  hours: number[]; pending_count: number; version: string; server_time: number;
}
export interface Session { configured: boolean; authenticated: boolean; csrf?: string; username?: string; must_change_password: boolean }
export interface Region { path: string; name: string }
export interface Settings { telegram_enabled: boolean; telegram_configured: boolean; public_url: string; version: string }
export const actions: Record<Action, string> = {
  snapshot: '系统快照', network: '网络检测', quality: 'IP 质量检测', patrol: '哨兵巡逻',
  google: '区域访问', trust: '本地站点访问', logs: '读取日志', update_data: '同步哨兵数据',
}
