import { ApiError } from "./bridge";
import { localizeRuntimeMessage } from "./localization";

function localizeOrDescribe(value: string): string {
  const localized = localizeRuntimeMessage(value);
  return localized === value
    ? `操作失败，请稍后重试。诊断信息：${value}`
    : localized;
}

export function errorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    const messages: Record<string, string> = {
      unauthorized: "本地服务拒绝了本次请求，请重新启动桌面应用。",
      request_failed: "本地服务请求失败，请稍后重试。",
      same_run: "请选择两个不同的运行进行对比。",
      runs_not_terminal: "两个运行都进入终止状态后才能对比。",
      run_not_found: "找不到指定的运行记录。",
      spec_not_found: "找不到指定的智能体版本。",
      duplicate_spec: "该智能体版本已存在，请创建一个新版本。",
      dataset_not_found: "找不到指定的评测数据集。",
      evaluation_batch_not_found: "找不到指定的评测批次。",
      duplicate_dataset: "该数据集的名称与版本已存在。",
      dataset_in_use: "数据集已被评测批次引用，不能删除。",
      validation_error: "提交内容不符合要求，请检查必填项、版本号与正则表达式。",
      invalid_evaluation_request: "评测请求无效，请确认基线批次与数据集一致。",
      provider_configuration_error: "模型连接配置不完整。",
      event_stream_failed: "运行事件流连接失败。",
    };
    return messages[error.code] ?? localizeOrDescribe(error.message);
  }
  if (error instanceof Error && error.message.trim()) {
    return localizeOrDescribe(error.message.trim());
  }
  if (typeof error === "string" && error.trim()) {
    return localizeOrDescribe(error.trim());
  }
  return "本地服务返回了未知错误，请重试。";
}
