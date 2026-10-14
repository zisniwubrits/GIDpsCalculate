/**
 * 错误边界：任何渲染期异常都显示成一张可读的错误卡片，**而不是白屏**。
 *
 * 为什么要有：白屏时用户拿不到任何信息（历史上就吃过一次 —— 「角色面板」弹窗读了
 * 旧后端没有的 `schema.panelMacros`，整页直接空白，只能靠猜）。这里至少把错误信息、
 * 组件栈和「重新加载」按钮摆出来，方便判断是旧后端还是真 bug。
 *
 * 注意：错误边界只能接住**渲染期**异常（React 的行为），事件回调里的异常要靠 try/catch。
 */
import { Component, type ErrorInfo, type ReactNode } from "react";

interface Props {
  children: ReactNode;
  /** 出错时额外显示的一段提示（比如"请重启后端服务"） */
  hint?: string;
}

interface State {
  error: Error | null;
}

export default class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    // 留在控制台里，方便进一步排查
    console.error("[dps] 渲染出错：", error, info.componentStack);
  }

  render() {
    const { error } = this.state;
    if (!error) return this.props.children;
    return (
      <div className="crash" role="alert" data-testid="crash">
        <h2>界面出错了</h2>
        <p className="crash-msg">{error.message || String(error)}</p>
        {this.props.hint ? <p className="dim">{this.props.hint}</p> : null}
        <p className="dim">
          常见原因：后端服务是旧进程（/api/schema 少了新字段）。请重启：
          双击 launcher.bat → [2] 停止 → [1] 启动，然后刷新本页。
        </p>        <div className="crash-actions">
          <button type="button" className="primary" onClick={() => window.location.reload()}>
            重新加载
          </button>
          <button type="button" onClick={() => this.setState({ error: null })}>
            尝试忽略并继续
          </button>
        </div>
      </div>
    );
  }
}
