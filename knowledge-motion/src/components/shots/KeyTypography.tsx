import React from "react";
import { AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";
import { KeyTypographyParams } from "../../types/schema";

export const KeyTypography: React.FC<{ params: KeyTypographyParams }> = ({ params }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  // 弹簧入场动效
  const entranceProgress = spring({
    frame,
    fps,
    config: { damping: 14, stiffness: 100 },
  });

  // 副标题延迟 12 帧入场
  const subtitleOpacity = interpolate(frame, [12, 25], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  const subtitleTranslateY = interpolate(frame, [12, 25], [30, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  const scale = interpolate(entranceProgress, [0, 1], [0.92, 1]);
  const opacity = interpolate(entranceProgress, [0, 1], [0, 1]);
  const translateY = interpolate(entranceProgress, [0, 1], [50, 0]);

  // 渲染带高亮的主标题
  const renderTitle = () => {
    if (!params.highlightWord) {
      return <span>{params.mainTitle}</span>;
    }
    const parts = params.mainTitle.split(params.highlightWord);
    return (
      <>
        {parts[0]}
        <span
          style={{
            color: "#38bdf8",
            textShadow: "0 0 25px rgba(56, 189, 248, 0.6)",
            padding: "0 10px",
            display: "inline-block",
            borderBottom: "4px solid #38bdf8",
          }}
        >
          {params.highlightWord}
        </span>
        {parts[1] || ""}
      </>
    );
  };

  return (
    <AbsoluteFill
      style={{
        justifyContent: "center",
        alignItems: "center",
        padding: "0 80px",
        textAlign: "center",
      }}
    >
      {/* 顶部标签 */}
      {params.badge && (
        <div
          style={{
            opacity,
            transform: `translateY(${translateY * 0.5}px)`,
            backgroundColor: "rgba(56, 189, 248, 0.15)",
            color: "#38bdf8",
            border: "1px solid rgba(56, 189, 248, 0.4)",
            padding: "8px 24px",
            borderRadius: 999,
            fontSize: 26,
            fontWeight: 600,
            letterSpacing: 2,
            marginBottom: 40,
            fontFamily: "monospace",
          }}
        >
          {params.badge}
        </div>
      )}

      {/* 主标题 */}
      <div
        style={{
          opacity,
          transform: `translateY(${translateY}px) scale(${scale})`,
          color: "#f8fafc",
          fontSize: 68,
          fontWeight: 800,
          lineHeight: 1.35,
          letterSpacing: -1,
          maxWidth: 920,
          textShadow: "0 10px 30px rgba(0,0,0,0.8)",
        }}
      >
        {renderTitle()}
      </div>

      {/* 副标题 */}
      {params.subtitle && (
        <div
          style={{
            opacity: subtitleOpacity,
            transform: `translateY(${subtitleTranslateY}px)`,
            marginTop: 45,
            color: "#94a3b8",
            fontSize: 34,
            lineHeight: 1.5,
            maxWidth: 820,
            fontWeight: 400,
          }}
        >
          {params.subtitle}
        </div>
      )}
    </AbsoluteFill>
  );
};
