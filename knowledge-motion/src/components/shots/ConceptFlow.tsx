import React from "react";
import { AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";
import { ConceptFlowParams } from "../../types/schema";

export const ConceptFlow: React.FC<{ params: ConceptFlowParams }> = ({ params }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  // 顶部入场
  const titleEntrance = spring({
    frame,
    fps,
    config: { damping: 14, stiffness: 100 },
  });

  return (
    <AbsoluteFill
      style={{
        justifyContent: "center",
        alignItems: "center",
        padding: "0 60px",
      }}
    >
      {/* 顶部标题 */}
      <div
        style={{
          textAlign: "center",
          marginBottom: 45,
          opacity: titleEntrance,
          transform: `translateY(${interpolate(titleEntrance, [0, 1], [30, 0])}px)`,
        }}
      >
        {params.badge && (
          <div
            style={{
              color: "#22c55e",
              fontFamily: "monospace",
              fontSize: 24,
              letterSpacing: 3,
              marginBottom: 12,
              fontWeight: 700,
            }}
          >
            {params.badge}
          </div>
        )}
        <div
          style={{
            color: "#ffffff",
            fontSize: 52,
            fontWeight: 800,
            letterSpacing: -1,
          }}
        >
          {params.title}
        </div>
      </div>

      {/* 流程节点列表 */}
      <div
        style={{
          width: "100%",
          display: "flex",
          flexDirection: "column",
          gap: 20,
          position: "relative",
        }}
      >
        {params.steps.map((stepText, idx) => {
          // 节点依次延迟点亮（第 8 帧、18 帧、28 帧、38 帧）
          const stepDelay = 8 + idx * 12;
          const nodeProgress = spring({
            frame: Math.max(0, frame - stepDelay),
            fps,
            config: { damping: 13, stiffness: 100 },
          });

          const isLit = frame >= stepDelay + 5;

          return (
            <div
              key={idx}
              style={{
                display: "flex",
                alignItems: "center",
                backgroundColor: isLit ? "rgba(6, 78, 59, 0.4)" : "rgba(15, 23, 42, 0.6)",
                border: `2px solid ${isLit ? "rgba(34, 197, 94, 0.7)" : "rgba(148, 163, 184, 0.2)"}`,
                borderRadius: 18,
                padding: "24px 28px",
                boxShadow: isLit ? "0 0 30px rgba(34, 197, 94, 0.2)" : "none",
                transform: `translateX(${interpolate(nodeProgress, [0, 1], [-40, 0])}px)`,
                opacity: nodeProgress,
                position: "relative",
              }}
            >
              {/* 序号发光圆标 */}
              <div
                style={{
                  width: 54,
                  height: 54,
                  borderRadius: "50%",
                  backgroundColor: isLit ? "#22c55e" : "#334155",
                  color: isLit ? "#050d0a" : "#94a3b8",
                  display: "flex",
                  justifyContent: "center",
                  alignItems: "center",
                  fontSize: 26,
                  fontWeight: 900,
                  marginRight: 24,
                  flexShrink: 0,
                  boxShadow: isLit ? "0 0 16px rgba(34, 197, 94, 0.6)" : "none",
                }}
              >
                0{idx + 1}
              </div>

              {/* 节点步骤描述 */}
              <div
                style={{
                  color: isLit ? "#f0fdf4" : "#94a3b8",
                  fontSize: 32,
                  fontWeight: isLit ? 700 : 500,
                  letterSpacing: 0.5,
                }}
              >
                {stepText}
              </div>

              {/* 右侧箭头标识（最后一个不显示） */}
              {idx < params.steps.length - 1 && (
                <div
                  style={{
                    marginLeft: "auto",
                    color: isLit ? "#22c55e" : "#475569",
                    fontSize: 28,
                    fontWeight: 900,
                  }}
                >
                  ↓
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* 底部摘要卡片 */}
      {params.summary && (
        <div
          style={{
            marginTop: 40,
            padding: "18px 30px",
            backgroundColor: "rgba(34, 197, 94, 0.1)",
            border: "1px dashed rgba(34, 197, 94, 0.4)",
            borderRadius: 14,
            color: "#86efac",
            fontSize: 26,
            textAlign: "center",
            maxWidth: 880,
            opacity: interpolate(frame, [35, 50], [0, 1], {
              extrapolateLeft: "clamp",
              extrapolateRight: "clamp",
            }),
          }}
        >
          🎯 {params.summary}
        </div>
      )}
    </AbsoluteFill>
  );
};
