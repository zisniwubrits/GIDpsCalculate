/** 顶部工具栏：工程名、保存目录、撤销/重做、文件操作、缩放、帮助与状态提示。 */
export interface ToolbarProps {
  name: string;
  onName: (v: string) => void;
  /** 一键保存的落地目录（后端记忆，点保存直接写到这里） */
  saveDir: string;
  dirty: boolean;
  canUndo: boolean;
  canRedo: boolean;
  onUndo: () => void;
  onRedo: () => void;
  onSave: () => void;
  onOpen: () => void;
  onExport: () => void;
  onClear: () => void;
  onHelp: () => void;
  zoom: number;
  onZoomIn: () => void;
  onZoomOut: () => void;
  onZoomReset: () => void;
  onFit: () => void;
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
        <button type="button" onClick={props.onClear} title="清空画布（可撤销）">
          清空
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
      </div>

      <div className="tb-right">
        <span className={`tb-status st-${status.kind}`} data-testid="status">
          {status.text}
        </span>
        <button type="button" className="tb-help" onClick={props.onHelp} title="F1">
          教程 (F1)
        </button>
      </div>
    </header>
  );
}
