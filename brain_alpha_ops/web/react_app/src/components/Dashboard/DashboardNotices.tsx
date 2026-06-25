export function SyncCloudCTA({ onNavigateToSync }: { onNavigateToSync: () => void }) {
  return (
    <div className="panel panel-warning mb-6">
      <div className="p-6">
        <div className="flex flex-col items-center text-center gap-3">
          <div
            className="w-14 h-14 rounded-full flex items-center justify-center"
            style={{ background: "var(--color-panel-warning-bg)" }}
          >
            <svg
              width="28"
              height="28"
              viewBox="0 0 24 24"
              fill="none"
              stroke="var(--color-warning-icon)"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <path d="M21.5 2v6h-6M2.5 22v-6h6M2 11.5a10 10 0 0 1 18.8-4.3M22 12.5a10 10 0 0 1-18.8 4.2" />
            </svg>
          </div>
          <div>
            <h2 className="text-lg font-semibold text-accent">连接成功！未检测到本地缓存</h2>
            <p className="text-sm text-text-secondary mt-1 max-w-md">
              BRAIN 连接正常。首次使用需要拉取云端 Alpha 列表和官方能力集；同步完成后，后续登录会默认直接读取本地缓存。
            </p>
          </div>
          <button
            type="button"
            className="btn btn-primary"
            onClick={onNavigateToSync}
            style={{ padding: "10px 32px", fontSize: 15, fontWeight: 600 }}
          >
            <svg
              width="16"
              height="16"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              className="mr-2"
            >
              <path d="M21.5 2v6h-6M2.5 22v-6h6M2 11.5a10 10 0 0 1 18.8-4.3M22 12.5a10 10 0 0 1-18.8 4.2" />
            </svg>
            开始首次同步
          </button>
          <p className="text-xs text-text-tertiary">
            后续刷新改为手动触发 · 同步过程中会显示实时进度和已等待时间
          </p>
        </div>
      </div>
    </div>
  );
}

export function CacheModeNotice() {
  return (
    <div className="panel panel-cache mb-4">
      <div className="panel-body-padded flex justify-between items-start gap-3">
        <div>
          <p className="text-sm font-medium text-warning mb-1">本地缓存可用，当前为缓存模式</p>
          <p className="text-xs text-text-secondary" style={{ lineHeight: 1.6 }}>
            可继续查看本地快照和候选信息；手动同步、官方回测和提交前复核需要先测试 BRAIN 连接。
          </p>
        </div>
      </div>
    </div>
  );
}

export function PhaseStatusNotice({ failed }: { failed: boolean }) {
  return (
    <div className={`panel mb-6 ${failed ? "panel-negative" : "panel-info"}`}>
      <div className="panel-body-padded">
        <p className={`text-sm font-medium mb-1 ${failed ? "text-negative" : "text-info"}`}>
          {failed ? "状态读取失败" : "正在读取本地状态"}
        </p>
        <p className="text-xs text-text-secondary" style={{ lineHeight: 1.6 }}>
          {failed
            ? "暂时无法确认账户连接和本地缓存状态；请刷新页面或重新打开本地控制台。"
            : "正在确认本地 session、云端 Alpha 缓存和官方上下文缓存；读取完成前不会判定为未连接。"}
        </p>
      </div>
    </div>
  );
}
