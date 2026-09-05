import { Icon } from "./Icon";

const suggestions: Array<[RegExp, string]> = [
  [/401|登录|session|unauthorized/i, "请重新登录后再试，未保存内容会继续保留在本机。"],
  [/403|权限|permission/i, "请确认当前账号具备该操作权限，或联系管理员调整角色。"],
  [/409|冲突|updated elsewhere|其他页面/i, "刷新并比较本机与云端版本，再选择要保留的内容。"],
  [/429|频繁|rate limit/i, "操作过于频繁，请稍等片刻后重试，避免连续点击。"],
  [/额度|quota|余额/i, "检查模型账户余额或切换到有可用额度的模型配置。"],
  [/认证|api.?key|authentication/i, "检查模型地址、模型名称和 API Key 是否匹配。"],
  [/网络|断流|timeout|超时/i, "检查网络和服务状态；已生成内容会保留，可从任务页恢复。"],
  [/参考解/i, "先查看失败的样例或测试点，再修正参考解或预期输出。"],
  [/生成器/i, "确保生成器输出包含 20–100 个唯一字符串的 JSON 数组。"],
  [/oracle|暴力解|对拍/i, "检查独立解能否处理生成器产生的小规模输入，并与参考解保持一致。"],
  [/存储|备份/i, "请先复制重要内容，并清理浏览器站点存储空间后重试。"],
];

export function friendlyError(message: string) {
  const mapped = suggestions.find(([pattern]) => pattern.test(message))?.[1];
  if (mapped) return mapped;
  // Structured API errors are already written for end users. Preserve their
  // concrete advice instead of replacing it with a generic second message.
  if (/[一-鿿]/.test(message)) return message;
  return "请检查填写内容与当前状态后重试；问题持续存在时可展开技术详情。";
}

export function ErrorNotice({
  message,
  title = "操作没有完成",
}: {
  message: string;
  title?: string;
}) {
  return (
    <section className="error-notice" role="alert">
      <div className="notice-icon"><Icon name="info" /></div>
      <div>
        <h3>{title}</h3>
        <p>{friendlyError(message)}</p>
        <details className="disclosure-card">
          <summary>查看技术详情</summary>
          <code>{message}</code>
        </details>
      </div>
    </section>
  );
}
