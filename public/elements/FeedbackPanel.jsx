import { Button } from "@/components/ui/button"
import { useState } from "react"

export default function FeedbackPanel(props) {
  const [suggestionOpen, setSuggestionOpen] = useState(false)
  const [suggestionText, setSuggestionText] = useState("")
  const [thankYou, setThankYou] = useState("")
  const feedbackState = props.feedbackState
  const autoCommentState = props.autoCommentState
  const suggestionState = props.suggestionState
  const feedbackLabel =
    feedbackState === "like"
      ? "✅ 已记录为👍 有帮助"
      : feedbackState === "dislike"
        ? "✅ 已记录为👎 需改进"
        : "未反馈"
  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
        <span>
          {feedbackLabel}
          {autoCommentState ? ` | 自动评论：${autoCommentState}` : ""}
          {suggestionState ? ` | 建议：${suggestionState}` : ""}
        </span>
        <Button
          size="sm"
          className="h-7 px-2 text-xs"
          variant={feedbackState === "like" ? "secondary" : "outline"}
          onClick={() => callAction({ name: "feedback", payload: { value: "like" } })}
        >
          👍 有帮助
        </Button>
        <Button
          size="sm"
          className="h-7 px-2 text-xs"
          variant={feedbackState === "dislike" ? "secondary" : "outline"}
          onClick={() => callAction({ name: "feedback", payload: { value: "dislike" } })}
        >
          👎 需改进
        </Button>
        {!autoCommentState?.includes("已添加到") && (
          <Button
            size="sm"
            className="h-7 px-2 text-xs"
            variant="outline"
            onClick={() => callAction({ name: "auto_comment", payload: { value: "add" } })}
          >
            📝 自动添加评论
          </Button>
        )}
        <Button
          size="sm"
          className="h-7 px-2 text-xs"
          variant={suggestionOpen ? "secondary" : "outline"}
          onClick={() => {
            setSuggestionOpen(true)
            setThankYou("")
          }}
        >
          💬 提交建议
        </Button>
      </div>
      {suggestionOpen && (
        <div className="flex flex-col gap-2 rounded-md border border-input p-2 text-xs">
          <textarea
            className="min-h-[80px] w-full rounded-md border border-input bg-background px-2 py-1 text-xs"
            value={suggestionText}
            placeholder="请输入你的建议"
            onChange={(event) => setSuggestionText(event.target.value)}
          />
          <div className="flex items-center gap-2">
            <Button
              size="sm"
              className="h-7 px-2 text-xs"
              onClick={() => {
                const trimmed = suggestionText.trim()
                if (!trimmed) {
                  return
                }
                callAction({
                  name: "suggestion_submit",
                  payload: { suggestion: trimmed },
                })
                setSuggestionText("")
                setSuggestionOpen(false)
                setThankYou("感谢你的建议！")
              }}
            >
              提交
            </Button>
            <Button
              size="sm"
              className="h-7 px-2 text-xs"
              variant="outline"
              onClick={() => {
                setSuggestionOpen(false)
              }}
            >
              取消
            </Button>
          </div>
        </div>
      )}
      {thankYou && <div className="text-xs text-muted-foreground">{thankYou}</div>}
    </div>
  )
}
