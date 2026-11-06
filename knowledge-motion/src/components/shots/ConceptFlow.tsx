import React from "react";
import { AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";
import { ConceptFlowParams } from "../../types/schema";

export const ConceptFlow: React.FC<{ params: ConceptFlowParams }> = ({ params }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  // 标题弹簧入场
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
      {/* 顶部徽标 */}
      {params.badge && (
        <div
          style={{
            opacity: titleEntrance,
            transform: `scale(${titleEntrance})`,
            backgroundColor: "rgba(16, 185, 129, 0.15)",
            color: "#10b981",
            border: "1px solid rgba(16, 185, 129, 0.4)",
            padding: "8px 24px",
            borderRadius: 999,
            fontSize: 24,
            fontWeight: 600,
            letterSpacing: 2,
            marginBottom: 25,
            fontFamily: "monospace",
          }}
        >
          {params.badge}
        </div>
      )}

      {/* 标题 */}
      <div
        style={{
          opacity: titleEntrance,
          color: "#f8fafc",
          fontSize: 56,
          fontWeight: 800,
          textAlign: "center",
          marginBottom: 60,
          maxWidth: 900,
          textShadow: "0 6px 20px rgba(0,0,0,0.6)",
        }}
      >
        {params.title}
      </div>

      {/* 纵向科技节点流程 */}
      <div
        style={{
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          width: "100%",
          maxWidth: 720,
          gap: 18,
        }}
      >
        {params.steps.map((step, idx) => {
          const stepDelay = 12 + idx * 16;
          const stepSpring = spring({
            frame: frame - stepDelay,
            fps,
            config: { damping: 15, stiffness: 120 },
          });

          const isVisible = frame >= stepDelay;
          const glowIntensity = Math.sin(frame * 0.15 + idx) * 0.2 + 0.8;

          return (
            <React.Fragment key={idx}>
              {/* 连接箭头 */}
              {idx > 0 && (
                <div
                  style={{
                    opacity: isVisible ? 1 : 0,
                    height: 30,
                    display: "flex",
                    flexDirection: "column",
                    alignItems: "center",
                    justifyContent: "center",
                  }}
                >
                  <div
                    style={{
                      width: 2,
                      height: 18,
                      backgroundColor: "#10b981",
                      boxShadow: "0 0 10px #10b981",
                    }}
                  />
                  <div
                    style={{
                      width: 0,
                      height: 0,
                      borderLeft: "6px solid transparent",
                      borderRight: "6px solid transparent",
                      borderTop: "8px solid #10b981",
                    }}
                  />
                </div>
              )}

              {/* 节点卡片 */}
              <div
                style={{
                  opacity: isVisible ? stepSpring : 0,
                  transform: `translateY(${isVisible ? (1 - stepSpring) * 30 : 30}px) scale(${isVisible ? stepSpring : 0.9})`,
                  width: "100%",
                  backgroundColor: "rgba(15, 23, 42, 0.85)",
                  border: "1px solid rgba(16, 185, 129, 0.4)",
                  borderRadius: 20,
                  padding: "24px 32px",
                  display: "flex",
                  alignItems: "center",
                  gap: 24,
                  boxShadow: `0 8px 32px rgba(0, 0, 0, 0.4), 0 0 ${15 * glowIntensity}px rgba(16, 185, 129, 0.2)`,
                }}
              >
                <div
                  style={{
                    width: 48,
                    height: 48,
                    borderRadius: 12,
                    backgroundColor: "#10b981",
                    color: "#0f172a",
                    display: "flex",
                    justifyContent: "center",
                    alignItems: "center",
                    fontSize: 24,
                    fontWeight: 800,
                    fontFamily: "monospace",
                    flexShrink: 0,
                  }}
                >
                  0{idx + 1}
                </div>
                <div
                  style={{
                    color: "#f1f5f9",
                    fontSize: 32,
                    fontWeight: 600,
                    letterSpacing: 0.5,
                  }}
                >
                  {step}
                </div>
              </div>
            </React.Fragment>
          );
        })}
      </div>

      {/* 底部总结 */}
      {params.summary && (
        <div
          style={{
            marginTop: 50,
            opacity: interpolate(frame, [50, 65], [0, 1], {
              extrapolateLeft: "clamp",
              extrapolateRight: "clamp",
            }),
            color: "#94a3b8",
            fontSize: 28,
            textAlign: "center",
            maxWidth: 820,
            lineHeight: 1.5,
            borderTop: "1px solid rgba(255,255,255,0.1)",
            paddingTop: 24,
          }}
        >
          {params.summary}
        </div>
      )}
    </AbsoluteFill>
  );
};
