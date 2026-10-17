/** 顶部工具栏：工程名、保存目录、撤销/重做、文件操作、缩放、帮助与状态提示。 */
import { displayWidthCh } from "../model";

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
  /** 是否显示域间箭头（角色 / 武器之间的拐力箭头，默认显示；只影响显示，不影响求值） */
  showDomainArrows: boolean;
  onToggleShowDomainArrows: () => void;
  status: { kind: "ok" | "warn" | "error" | "busy"; text: string };
}

export default function Toolbar(props: ToolbarProps) {
  const { status } = props;
  return (
    <header className="toolbar" data-testid="toolbar">
      <div className="tb-left">
        <label className="tb-name">
          <span>工程名</span>
          {/* 输入框按内容自适应宽度（ch = 等宽字体的一个字符宽），名字再长也能整串看见 */}
          <input
            value={props.name}
            placeholder="未命名"
            data-testid="project-name"
            style={{ width: `${Math.max(displayWidthCh(props.name || "未命名") + 2, 8)}ch` }}
            title={props.name || "未命名"}
            onChange={(e) => props.onName(e.target.value)}
          />
        </label>
        <span className={`tb-dirty${props.dirty ? " on" : ""}`} title="是否有未保存到文件的修改">
          {props.dirty ? "● 未保存" : "○ 已保存"}
        </span>
        {props.saveDir ? (
          // 目录完整显示并允许换行（原来超长会被省略号截掉，看不出存到哪）
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
        {/* 显示开关：关掉只藏箭头，连线仍在工程里、拐力照旧生效 */}
        <button
          type="button"
          className={`tb-toggle${props.showDomainArrows ? " on" : ""}`}
          data-testid="show-domain-arrows"
          aria-pressed={props.showDomainArrows}
          onClick={props.onToggleShowDomainArrows}
          title={
            props.showDomainArrows
              ? "正在显示域间箭头（角色 / 武器之间的拐力箭头）。点一下隐藏，方便看清卡片"
              : "域间箭头已隐藏（拐力照样生效）。点一下显示"
          }
        >
          域间箭头
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
