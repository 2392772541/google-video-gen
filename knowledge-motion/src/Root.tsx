import React from "react";
import { Composition } from "remotion";
import { KnowledgeMotionComposition } from "./Composition";
import { ProjectDSLSchema } from "./types/schema";
import rawProject from "./alginate-project.json";

// Zod 强校验确保配置合法
const validatedProject = ProjectDSLSchema.parse(rawProject);
const totalFrames = validatedProject.shots.reduce((acc, shot) => acc + shot.durationInFrames, 0);

export const RemotionRoot: React.FC = () => {
  return (
    <Composition
      id="Main"
      component={KnowledgeMotionComposition}
      durationInFrames={totalFrames}
      fps={validatedProject.fps}
      width={validatedProject.width}
      height={validatedProject.height}
      defaultProps={{
        project: validatedProject,
      }}
    />
  );
};
