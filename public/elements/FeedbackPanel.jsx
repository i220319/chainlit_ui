import { Button } from "@/components/ui/button"

export default function FeedbackPanel() {
  const feedbackState = props.feedbackState
  const autoCommentState = props.autoCommentState
  const feedbackLabel =
    feedbackState === "up"
      ? "✅ 已记录为👍 有帮助"
      : feedbackState === "down"
        ? "✅ 已记录为👎 需改进"
        : "未反馈"
  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
        <span>
          {feedbackLabel}
          {autoCommentState ? ` | 自动评论：${autoCommentState}` : ""}
        </span>
        <Button
          size="sm"
          className="h-7 px-2 text-xs"
          variant={feedbackState === "up" ? "secondary" : "outline"}
          onClick={() => callAction({ name: "feedback", payload: { value: "up" } })}
        >
          👍 有帮助
        </Button>
        <Button
          size="sm"
          className="h-7 px-2 text-xs"
          variant={feedbackState === "down" ? "secondary" : "outline"}
          onClick={() => callAction({ name: "feedback", payload: { value: "down" } })}
        >
          👎 需改进
        </Button>
        <Button
          size="sm"
          className="h-7 px-2 text-xs"
          onClick={() => callAction({ name: "auto_comment", payload: { value: "add" } })}
        >
          📝 自动添加评论
        </Button>
      </div>
    </div>
  )
}
