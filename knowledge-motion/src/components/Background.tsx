import React from "react";
import { AbsoluteFill, useCurrentFrame } from "remotion";

interface BackgroundProps {
  theme?: "cyber_dark" | "matrix_green" | "crimson_hazard";
}

export const Background: React.FC<BackgroundProps> = ({ theme = "cyber_dark" }) => {
  const frame = useCurrentFrame();

  const themeColors = {
    cyber_dark: {
      bg: "#07090e",
      grid: "rgba(56, 189, 248, 0.05)",
      glow: "rgba(14, 165, 233, 0.12)",
    },
    matrix_green: {
      bg: "#050d0a",
      grid: "rgba(34, 197, 94, 0.06)",
      glow: "rgba(16, 185, 129, 0.12)",
    },
    crimson_hazard: {
      bg: "#0d0608",
      grid: "rgba(239, 68, 68, 0.06)",
      glow: "rgba(225, 29, 72, 0.12)",
    },
  };

  const current = themeColors[theme] || themeColors.cyber_dark;
  const scanlineOffset = (frame * 2) % 40;

  return (
    <AbsoluteFill
      style={{
        backgroundColor: current.bg,
        overflow: "hidden",
      }}
    >
      {/* 科技感大光晕 */}
      <div
        style={{
          position: "absolute",
          top: "20%",
          left: "50%",
          transform: "translate(-50%, -50%)",
          width: 900,
          height: 900,
          borderRadius: "50%",
          background: `radial-gradient(circle, ${current.glow} 0%, rgba(0,0,0,0) 70%)`,
          filter: "blur(60px)",
          pointerEvents: "none",
        }}
      />

      {/* 基础网格 */}
      <div
        style={{
          position: "absolute",
          inset: 0,
          backgroundImage: `
            linear-gradient(to right, ${current.grid} 1px, transparent 1px),
            linear-gradient(to bottom, ${current.grid} 1px, transparent 1px)
          `,
          backgroundSize: "60px 60px",
          backgroundPosition: `0px ${scanlineOffset}px`,
        }}
      />

      {/* 顶部微光装饰标尺 */}
      <div
        style={{
          position: "absolute",
          top: 60,
          left: 60,
          right: 60,
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          borderBottom: `1px solid ${current.grid}`,
          paddingBottom: 15,
          color: "rgba(255,255,255,0.35)",
          fontSize: 22,
          fontFamily: "monospace",
          letterSpacing: 3,
        }}
      >
        <span>KNOWLEDGE MOTION // AI_LAB</span>
        <span>FRAME {String(frame).padStart(4, "0")}</span>
      </div>
    </AbsoluteFill>
  );
};
