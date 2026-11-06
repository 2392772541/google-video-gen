import React, { useMemo } from "react";
import { AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";
import { NoiseDisruptorParams } from "../../types/schema";

export const NoiseDisruptor: React.FC<{ params: NoiseDisruptorParams }> = ({ params }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  // 0~15 帧：卡片正常入场
  const cardEntrance = spring({
    frame,
    fps,
    config: { damping: 15, stiffness: 90 },
  });

  // 第 25 帧开始：噪点注入攻击
  const attackStartFrame = 25;
  const isAttacked = frame >= attackStartFrame;

  const noiseProgress = interpolate(frame, [attackStartFrame, attackStartFrame + 15], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  // 故障抖动
  const glitchX = isAttacked ? (Math.sin(frame * 1.5) * 6 * noiseProgress) : 0;
  const glitchY = isAttacked ? (Math.cos(frame * 2.1) * 4 * noiseProgress) : 0;

  // 纯程序化生成 400 个点阵像素（模拟图像数据矩阵）
  const gridPixels = useMemo(() => {
    const pixels = [];
    for (let r = 0; r < 14; r++) {
      for (let c = 0; c < 14; c++) {
        // 中心区域亮，外围暗，形成一个类似特征图案
        const distFromCenter = Math.hypot(r - 6.5, c - 6.5);
        const baseBrightness = Math.max(0.15, 1 - distFromCenter / 8);
        pixels.push({ r, c, baseBrightness });
      }
    }
    return pixels;
  }, []);

  return (
    <AbsoluteFill
      style={{
        justifyContent: "center",
        alignItems: "center",
        padding: "0 60px",
      }}
    >
      {/* 顶部指示器 */}
      <div
        style={{
          marginBottom: 30,
          textAlign: "center",
          opacity: cardEntrance,
        }}
      >
        <div
          style={{
            color: isAttacked ? "#ef4444" : "#38bdf8",
            fontFamily: "monospace",
            fontSize: 24,
            letterSpacing: 2,
            marginBottom: 10,
            fontWeight: 700,
          }}
        >
          {isAttacked ? "[ ALERT: ADVERSARIAL PERTURBATION DETECTED ]" : "[ STATUS: NORMAL INFERENCE ]"}
        </div>
        <div style={{ color: "#ffffff", fontSize: 48, fontWeight: 800 }}>
          {params.title}
        </div>
      </div>

      {/* 中间核心受攻击图像框 */}
      <div
        style={{
          position: "relative",
          width: 640,
          height: 640,
          backgroundColor: "#0d131f",
          borderRadius: 24,
          border: `2px solid ${isAttacked ? "rgba(239, 68, 68, 0.6)" : "rgba(56, 189, 248, 0.4)"}`,
          boxShadow: isAttacked
            ? "0 0 50px rgba(239, 68, 68, 0.3)"
            : "0 0 40px rgba(56, 189, 248, 0.15)",
          overflow: "hidden",
          transform: `translate(${glitchX}px, ${glitchY}px) scale(${cardEntrance})`,
          display: "flex",
          justifyContent: "center",
          alignItems: "center",
        }}
      >
        {/* 点阵网格展示 */}
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(14, 32px)",
            gridGap: 6,
          }}
        >
          {gridPixels.map((p, idx) => {
            // 受到噪点影响时，随机点亮度发生异化
            const noiseFluctuation = isAttacked
              ? Math.sin(idx * 77 + frame * 0.8) * 0.6 * noiseProgress
              : 0;
            const brightness = Math.max(0.05, Math.min(1, p.baseBrightness + noiseFluctuation));
            const color = isAttacked && Math.abs(noiseFluctuation) > 0.3
              ? `rgb(239, ${Math.floor(brightness * 68)}, 68)`
              : `rgb(${Math.floor(brightness * 56)}, ${Math.floor(brightness * 189)}, ${Math.floor(brightness * 248)})`;

            return (
              <div
                key={idx}
                style={{
                  width: 32,
                  height: 32,
                  backgroundColor: color,
                  borderRadius: 4,
                  boxShadow: brightness > 0.7 ? `0 0 8px ${color}` : "none",
                }}
              />
            );
          })}
        </div>

        {/* 覆盖的微小随机噪点层 */}
        {isAttacked && (
          <div
            style={{
              position: "absolute",
              inset: 0,
              opacity: noiseProgress * params.noiseIntensity * 0.7,
              backgroundImage: `radial-gradient(#ffffff 1px, transparent 1px)`,
              backgroundSize: "8px 8px",
              backgroundPosition: `${(frame * 13) % 20}px ${(frame * 17) % 20}px`,
              mixBlendMode: "screen",
              pointerEvents: "none",
            }}
          />
        )}
      </div>

      {/* 下方分类标签突变条 */}
      <div
        style={{
          marginTop: 40,
          width: 640,
          backgroundColor: "rgba(15, 23, 42, 0.85)",
          borderRadius: 16,
          padding: "24px 30px",
          border: "1px solid rgba(255, 255, 255, 0.1)",
          transform: `scale(${cardEntrance})`,
        }}
      >
        <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 14 }}>
          <span style={{ color: "#94a3b8", fontSize: 24 }}>模型判定结果</span>
          <span
            style={{
              color: isAttacked ? "#ef4444" : "#22c55e",
              fontSize: 26,
              fontWeight: 700,
              fontFamily: "monospace",
            }}
          >
            {isAttacked ? params.labelAfter : params.labelBefore}
          </span>
        </div>

        {/* 置信度进度条 */}
        <div
          style={{
            width: "100%",
            height: 14,
            backgroundColor: "rgba(255, 255, 255, 0.1)",
            borderRadius: 7,
            overflow: "hidden",
          }}
        >
          <div
            style={{
              height: "100%",
              width: isAttacked ? "99.3%" : "57.7%",
              backgroundColor: isAttacked ? "#ef4444" : "#22c55e",
              boxShadow: isAttacked ? "0 0 16px #ef4444" : "0 0 16px #22c55e",
              transition: "width 0.3s ease-out, background-color 0.3s",
            }}
          />
        </div>
      </div>
    </AbsoluteFill>
  );
};
