/** 顶部工具栏：工程名、保存目录、撤销/重做、文件操作、缩放、帮助与状态提示。 */
export interface ToolbarProps {
  name: string;
  onName: (v: string) => void;
  /** 一键保存的落地目录（后端记忆，点保存直接写到这里） */
  saveDir: string;
  /** 前端产物过期提示（非空时在工具栏显示一条警告） */
  staleHint?: string;
  /** 后端报的前端产物构建时间：显示出来便于确认浏览器加载的是不是最新包 */
  buildTime?: string;
  dirty: boolean;
  canUndo: boolean;
  canRedo: boolean;
  onUndo: () => void;
  onRedo: () => void;
  onSave: () => void;
  onOpen: () => void;
  onExport: () => void;
  onNewProject: () => void;
  onHelp: () => void;
  zoom: number;
  onZoomIn: () => void;
  onZoomOut: () => void;
  onZoomReset: () => void;
  onFit: () => void;
  /** 框选时是否把**角色 / 武器域**也一起选中（默认关：域是大面板，开了很容易整块被框进来） */
  boxSelectDomains: boolean;
  onToggleBoxSelectDomains: () => void;
  status: { kind: "ok" | "warn" | "error" | "busy"; text: string };
}

export default function Toolbar(props: ToolbarProps) {
  const { status } = props;
  return (
    <header className="toolbar" data-testid="toolbar">
      <div className="tb-left">
        <label className="tb-name">
          <span>工程名</span>
          <input
            value={props.name}
            placeholder="未命名"
            data-testid="project-name"
            onChange={(e) => props.onName(e.target.value)}
          />
        </label>
        <span className={`tb-dirty${props.dirty ? " on" : ""}`} title="是否有未保存到文件的修改">
          {props.dirty ? "● 未保存" : "○ 已保存"}
        </span>
        {props.saveDir ? (
          <span className="tb-dir" title={`一键保存会写到这里：${props.saveDir}`} data-testid="save-dir">
            保存到：{props.saveDir}
          </span>
        ) : null}
      </div>

      <div className="tb-mid">
        <button type="button" onClick={props.onUndo} disabled={!props.canUndo} title="Ctrl+Z">
          撤销
        </button>
        <button type="button" onClick={props.onRedo} disabled={!props.canRedo} title="Ctrl+Shift+Z / Ctrl+Y">
          重做
        </button>
        <span className="tb-sep" />
        <button type="button" onClick={props.onSave} title="导出为 JSON 文件">
          保存工程…
        </button>
        <button type="button" onClick={props.onOpen} title="从 JSON 文件导入">
          打开工程…
        </button>
        <button type="button" onClick={props.onExport} title="导出可读文本报告">
          导出结果…
        </button>
        <button
          type="button"
          onClick={props.onNewProject}
          data-testid="new-project"
          title="新建项目：先问工程名，再清空画布 / 撤销历史 / 本地自动存档"
        >
          新建…
        </button>
        <span className="tb-sep" />
        <button type="button" onClick={props.onZoomOut} title="缩小 (Ctrl+滚轮)">
          －
        </button>
        <button type="button" onClick={props.onZoomReset} title="重置为 100%">
          {Math.round(props.zoom * 100)}%
        </button>
        <button type="button" onClick={props.onZoomIn} title="放大 (Ctrl+滚轮)">
          ＋
        </button>
        <button type="button" onClick={props.onFit} title="缩放到适合画布内容">
          适应
        </button>
        <span className="tb-sep" />
        {/* 框选开关：默认关 —— 关时框选只选普通卡片，角色/武器域要单独点标题栏。
            开了之后框选会把域一起选进来（注意：此时 Delete 会连域一起删）。 */}
        <button
          type="button"
          className={`tb-toggle${props.boxSelectDomains ? " on" : ""}`}
          data-testid="box-select-domains"
          aria-pressed={props.boxSelectDomains}
          onClick={props.onToggleBoxSelectDomains}
          title={
            props.boxSelectDomains
              ? "框选会连角色 / 武器域一起选中（此时 Delete 会连域一起删）。再点一次关掉"
              : "框选时是否也选角色 / 武器域：现在关着，框选只选普通卡片（想选域请点它的标题栏）"
          }
        >
          框选域
        </button>
      </div>

      <div className="tb-right">
        <span className={`tb-status st-${status.kind}`} data-testid="status">
          {status.text}
        </span>
        {props.staleHint ? (
          <span className="tb-stale" title={props.staleHint} data-testid="stale-hint">
            ⚠ 前端产物过期
          </span>
        ) : null}
        {props.buildTime ? (
          <span
            className="tb-build"
            data-testid="build-time"
            title={`当前这一步前端产物的构建时间：${props.buildTime}。若浏览器里显示的不是最新改动，先 Ctrl+F5 强制刷新（旧包会被浏览器缓存）。`}
          >
            构建 {props.buildTime.slice(5, 16)}
          </span>
        ) : null}
        <button type="button" className="tb-help" onClick={props.onHelp} title="F1">
          教程 (F1)
        </button>
      </div>
    </header>
  );
}
