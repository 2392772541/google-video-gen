import React from "react";
import { AbsoluteFill, Series } from "remotion";
import { ProjectDSL } from "./types/schema";
import { Background } from "./components/Background";
import { KeyTypography } from "./components/shots/KeyTypography";
import { NoiseDisruptor } from "./components/shots/NoiseDisruptor";

export const KnowledgeMotionComposition: React.FC<{ project: ProjectDSL }> = ({ project }) => {
  return (
    <AbsoluteFill>
      {/* 全局科技风背景 */}
      <Background theme={project.theme} />

      {/* 镜头序列时间轴 */}
      <Series>
        {project.shots.map((shot) => {
          return (
            <Series.Sequence
              key={shot.id}
              durationInFrames={shot.durationInFrames}
              name={`${shot.type}_${shot.id}`}
            >
              {shot.type === "KeyTypography" && <KeyTypography params={shot} />}
              {shot.type === "NoiseDisruptor" && <NoiseDisruptor params={shot} />}
            </Series.Sequence>
          );
        })}
      </Series>
    </AbsoluteFill>
  );
};
