/** 左侧菜单：添加卡片（按后端 schema 分组）、一键预设、选中卡片的对齐操作。 */
import type { AlignMode } from "../model";
import type { Schema } from "../types";

export interface SidebarProps {
  schema: Schema;
  selectedCount: number;
  onAdd: (type: string) => void;
  onPreset: (name: string) => void;
  onAlign: (mode: AlignMode) => void;
  onClear: () => void;
  onClearSelection: () => void;
}

const ALIGN_OPS: { mode: AlignMode; label: string }[] = [
  { mode: "left", label: "左对齐" },
  { mode: "top", label: "顶对齐" },
  { mode: "hcenter", label: "水平居中" },
  { mode: "vcenter", label: "垂直居中" },
];

export default function Sidebar({
  schema,
  selectedCount,
  onAdd,
  onPreset,
  onAlign,
  onClear,
  onClearSelection,
}: SidebarProps) {
  return (
    <aside className="sidebar" data-testid="sidebar">
      {schema.groups.map((group) => (
        <section className="side-group" key={group.name}>
          <h3>{group.name}</h3>
          <div className="side-items">
            {group.items.map((item) => (
              <button
                type="button"
                key={item.type}
                className="side-btn"
                data-testid={`add-${item.type}`}
                onClick={() => onAdd(item.type)}
              >
                {item.label}
              </button>
            ))}
          </div>
        </section>
      ))}

      <section className="side-group">
        <h3>一键预设</h3>
        <div className="side-items">
          {Object.keys(schema.presets).map((name) => (
            <button
              type="button"
              key={name}
              className="side-btn"
              data-testid={`preset-${name}`}
              onClick={() => onPreset(name)}
            >
              {name}
            </button>
          ))}
        </div>
        <button type="button" className="side-btn side-danger" onClick={onClear}>
          清空画布
        </button>
      </section>

      <section className="side-group">
        <h3>选中的卡片</h3>
        <p className="side-hint">
          {selectedCount > 0
            ? `已选 ${selectedCount} 张（Shift 点选 / 框选）`
            : "已选 0 张（Shift 点选 / 框选）"}
        </p>
        <div className="side-items">
          {ALIGN_OPS.map((op) => (
            <button
              type="button"
              key={op.mode}
              className="side-btn"
              disabled={selectedCount < 2}
              onClick={() => onAlign(op.mode)}
            >
              {op.label}
            </button>
          ))}
        </div>
        <button
          type="button"
          className="side-btn"
          disabled={selectedCount === 0}
          onClick={onClearSelection}
        >
          取消选择
        </button>
      </section>
    </aside>
  );
}
