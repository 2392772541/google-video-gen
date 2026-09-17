import React, { useRef } from "react";
import type { PropField } from "../cards/types";
import { CARDS } from "../cards/registry";
import { findClip, useStore } from "../store";
import { seekTo } from "../playerRef";

/** 单个属性控件：按 schema 字段类型渲染 */
const PropControl: React.FC<{
  field: PropField;
  value: unknown;
  onChange: (v: unknown) => void;
  onBegin: () => void;
}> = ({ field, value, onChange, onBegin }) => {
  switch (field.type) {
    case "text":
      return (
        <input
          type="text"
          value={String(value ?? "")}
          onFocus={onBegin}
          onChange={(e) => onChange(e.target.value)}
        />
      );
    case "textarea":
      return (
        <textarea
          rows={3}
          value={String(value ?? "")}
          onFocus={onBegin}
          onChange={(e) => onChange(e.target.value)}
        />
      );
    case "number":
      return (
        <span className="ctl-row">
          <input
            type="number"
            value={Number(value ?? 0)}
            min={field.min}
            max={field.max}
            step={field.step ?? 1}
            onFocus={onBegin}
            onChange={(e) => onChange(Number(e.target.value))}
          />
          {field.unit && <span className="unit">{field.unit}</span>}
        </span>
      );
    case "slider":
      return (
        <span className="ctl-row">
          <input
            type="range"
            value={Number(value ?? field.default)}
            min={field.min}
            max={field.max}
            step={field.step}
            onPointerDown={onBegin}
            onChange={(e) => onChange(Number(e.target.value))}
          />
          <span className="slider-val">
            {Number(value ?? field.default)}
            {field.unit ?? ""}
          </span>
        </span>
      );
    case "color":
      return (
        <span className="ctl-row">
          <input
            type="color"
            value={String(value ?? field.default)}
            onFocus={onBegin}
            onChange={(e) => onChange(e.target.value)}
          />
          <input
            type="text"
            className="color-text"
            value={String(value ?? field.default)}
            onFocus={onBegin}
            onChange={(e) => onChange(e.target.value)}
          />
        </span>
      );
    case "select":
      return (
        <select
          value={String(value ?? field.default)}
          onFocus={onBegin}
          onChange={(e) => onChange(e.target.value)}
        >
          {field.options.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>
      );
    case "boolean":
      return (
        <input
          type="checkbox"
          checked={Boolean(value ?? field.default)}
          onChange={(e) => {
            onBegin();
            onChange(e.target.checked);
          }}
        />
      );
  }
};

const Row: React.FC<{ label: string; children: React.ReactNode }> = ({ label, children }) => (
  <label className="prop-row">
    <span className="prop-label">{label}</span>
    <span className="prop-ctl">{children}</span>
  </label>
);

export const Inspector: React.FC = () => {
  const project = useStore((s) => s.project);
  const selectedClipId = useStore((s) => s.selectedClipId);
  const previewItem = useStore((s) => s.previewItem);
  const setPreview = useStore((s) => s.setPreview);
  const addClip = useStore((s) => s.addClip);
  const updateClip = useStore((s) => s.updateClip);
  const updateClipProps = useStore((s) => s.updateClipProps);
  const removeClip = useStore((s) => s.removeClip);
  const commit = useStore((s) => s.commit);

  // 连续编辑合并为一步撤销：间隔 >800ms 才压新快照
  const lastBeginRef = useRef(0);

  if (previewItem) {
    if (previewItem.kind === "card") {
      const previewCard = CARDS[previewItem.cardId];
      return (
        <div className="inspector">
          <div className="panel-title" style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <span>{previewCard?.name ?? previewItem.cardId}</span>
            <span style={{ fontSize: 11, background: "#3b82f6", color: "#fff", padding: "2px 6px", borderRadius: 4, fontWeight: 500 }}>
              素材库预览
            </span>
          </div>
          <div style={{ padding: "14px", display: "flex", flexDirection: "column", gap: 12 }}>
            <div style={{ background: "rgba(59, 130, 246, 0.12)", border: "1px solid rgba(59, 130, 246, 0.3)", borderRadius: 6, padding: "10px 12px", fontSize: 12, lineHeight: 1.6, color: "#bfdbfe" }}>
              💡 <strong>当前为动效素材预览模式</strong><br />
              此卡片尚未插入时间轴。点击下方按钮添加到时间轴后，即可在此实时修改文字、高亮色彩与图层动画参数！
            </div>

            <button
              className="btn primary"
              style={{
                height: 38,
                fontSize: 13,
                fontWeight: 600,
                background: "linear-gradient(135deg, #4f46e5 0%, #7c3aed 100%)",
                borderColor: "#6366f1",
                boxShadow: "0 2px 8px rgba(79, 70, 229, 0.3)"
              }}
              onClick={() => {
                addClip(previewItem.cardId);
                setPreview(null);
              }}
            >
              ➕ 插入到时间轴并编辑
            </button>

            {previewCard && (
              <div style={{ marginTop: 4 }}>
                <div className="sec-title" style={{ marginBottom: 6 }}>可调参数一览</div>
                <div style={{ fontSize: 12, color: "#cbd5e1", display: "flex", flexDirection: "column", gap: 6 }}>
                  {previewCard.schema.map((f) => (
                    <div
                      key={f.key}
                      style={{
                        display: "flex",
                        justifyContent: "space-between",
                        alignItems: "center",
                        padding: "4px 8px",
                        background: "rgba(255,255,255,0.03)",
                        borderRadius: 4
                      }}
                    >
                      <span style={{ fontWeight: 500 }}>{f.label || f.key}</span>
                      <span style={{ color: "#64748b", fontSize: 11 }}>
                        {f.type === "text" ? "文本" : f.type === "color" ? "颜色" : f.type === "slider" ? "滑块" : f.type}
                      </span>
                    </div>
                  ))}
                  {previewCard.schema.length === 0 && (
                    <div style={{ color: "#64748b", fontStyle: "italic" }}>该卡片无额外可配置参数</div>
                  )}
                </div>
              </div>
            )}

            <button
              className="btn"
              style={{ marginTop: 10 }}
              onClick={() => setPreview(null)}
            >
              ✕ 退出预览，返回工程
            </button>
          </div>
        </div>
      );
    }
    return (
      <div className="inspector">
        <div className="panel-title">{previewItem.label}</div>
        <div style={{ padding: 14 }}>
          <button className="btn" onClick={() => setPreview(null)}>
            ✕ 退出预览
          </button>
        </div>
      </div>
    );
  }

  const hit = selectedClipId ? findClip(project, selectedClipId) : null;

  if (!hit) {
    return (
      <div className="inspector">
        <div className="panel-title">属性</div>
        <div className="inspector-empty dim">
          选中时间轨上的片段后，
          <br />
          在这里调整它的文字、颜色、
          <br />
          动画节奏、变速与图层属性。
          <br />
          <br />
          快捷键：空格 播放 · S 分割
          <br />
          Delete 删除 · ⌘Z 撤销 · ⌘D 复制
        </div>
      </div>
    );
  }

  const { track, clip } = hit;
  const card = CARDS[clip.cardId];
  const fps = project.fps;
  // 每次编辑手势开始压一次撤销快照；短时间内的连续输入合并为一步
  const begin = () => {
    const now = Date.now();
    if (now - lastBeginRef.current > 800) commit();
    lastBeginRef.current = now;
  };

  return (
    <div className="inspector">
      <div className="panel-title" style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <div style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
          {card?.name ?? clip.cardId}
          <span className="dim" style={{ marginLeft: 8, fontWeight: 400 }}>
            {track.name}
          </span>
        </div>
        <button
          className="btn"
          style={{
            fontSize: 11,
            padding: "2px 8px",
            height: 24,
            background: "rgba(99, 102, 241, 0.15)",
            color: "#a5b4fc",
            border: "1px solid rgba(99, 102, 241, 0.35)",
            borderRadius: 4,
            cursor: "pointer",
            flexShrink: 0,
            marginLeft: 8,
          }}
          title="将播放头移动到此片段并刷新画面"
          onClick={() => {
            const targetFrame = clip.start + Math.min(25, Math.floor(clip.duration / 3));
            useStore.getState().setPlayhead(targetFrame);
            seekTo(targetFrame);
          }}
        >
          🎯 定位至此
        </button>
      </div>

      <div className="inspector-scroll">
        {card && card.schema.length > 0 && (
          <section>
            <div className="sec-title">内容与样式</div>
            {card.schema.map((field) => (
              <Row key={field.key} label={field.label}>
                <PropControl
                  field={field}
                  value={clip.props[field.key] ?? field.default}
                  onChange={(v) => updateClipProps(clip.id, { [field.key]: v })}
                  onBegin={begin}
                />
              </Row>
            ))}
          </section>
        )}

        <section>
          <div className="sec-title">时间与变速</div>
          <Row label="起点">
            <span className="ctl-row">
              <input
                type="number"
                value={Number((clip.start / fps).toFixed(2))}
                min={0}
                step={0.1}
                onFocus={begin}
                onChange={(e) =>
                  updateClip(clip.id, { start: Math.max(0, Math.round(Number(e.target.value) * fps)) })
                }
              />
              <span className="unit">s</span>
            </span>
          </Row>
          <Row label="时长">
            <span className="ctl-row">
              <input
                type="number"
                value={Number((clip.duration / fps).toFixed(2))}
                min={2 / fps}
                step={0.1}
                onFocus={begin}
                onChange={(e) =>
                  updateClip(clip.id, {
                    duration: Math.max(2, Math.round(Number(e.target.value) * fps)),
                  })
                }
              />
              <span className="unit">s</span>
            </span>
          </Row>
          <Row label="变速">
            <span className="ctl-row">
              <input
                type="range"
                min={0.25}
                max={4}
                step={0.05}
                value={clip.speed}
                onPointerDown={begin}
                onChange={(e) => updateClip(clip.id, { speed: Number(e.target.value) })}
              />
              <span className="slider-val">{clip.speed}×</span>
            </span>
          </Row>
          <Row label="">
            <span className="ctl-row preset-row">
              {[0.5, 1, 1.5, 2].map((v) => (
                <button
                  key={v}
                  className={`mini preset${clip.speed === v ? " on" : ""}`}
                  onClick={() => {
                    begin();
                    updateClip(clip.id, { speed: v });
                  }}
                >
                  {v}×
                </button>
              ))}
            </span>
          </Row>
          <Row label="裁入点">
            <span className="ctl-row">
              <input
                type="number"
                value={Number((clip.inOffset / fps).toFixed(2))}
                min={0}
                step={0.1}
                onFocus={begin}
                onChange={(e) =>
                  updateClip(clip.id, {
                    inOffset: Math.max(0, Math.round(Number(e.target.value) * fps)),
                  })
                }
              />
              <span className="unit">s</span>
            </span>
          </Row>
          {card && (
            <Row label="">
              <button
                className="mini"
                title="时长恢复为卡片原始时长（按当前变速换算）"
                onClick={() => {
                  begin();
                  updateClip(clip.id, {
                    duration: Math.max(
                      2,
                      Math.round((card.durationInFrames - clip.inOffset) / clip.speed),
                    ),
                  });
                }}
              >
                ↺ 恢复原始时长
              </button>
            </Row>
          )}
        </section>

        <section>
          <div className="sec-title">图层</div>
          <Row label="不透明度">
            <span className="ctl-row">
              <input
                type="range"
                min={0}
                max={1}
                step={0.01}
                value={clip.opacity}
                onPointerDown={begin}
                onChange={(e) => updateClip(clip.id, { opacity: Number(e.target.value) })}
              />
              <span className="slider-val">{Math.round(clip.opacity * 100)}%</span>
            </span>
          </Row>
          <Row label="缩放">
            <span className="ctl-row">
              <input
                type="range"
                min={0.2}
                max={3}
                step={0.01}
                value={clip.scale}
                onPointerDown={begin}
                onChange={(e) => updateClip(clip.id, { scale: Number(e.target.value) })}
              />
              <span className="slider-val">{clip.scale.toFixed(2)}</span>
            </span>
          </Row>
          <Row label="位移 X">
            <span className="ctl-row">
              <input
                type="number"
                value={clip.x}
                step={2}
                onFocus={begin}
                onChange={(e) => updateClip(clip.id, { x: Number(e.target.value) })}
              />
              <span className="unit">px</span>
            </span>
          </Row>
          <Row label="位移 Y">
            <span className="ctl-row">
              <input
                type="number"
                value={clip.y}
                step={2}
                onFocus={begin}
                onChange={(e) => updateClip(clip.id, { y: Number(e.target.value) })}
              />
              <span className="unit">px</span>
            </span>
          </Row>
        </section>

        <section>
          <button className="btn danger" onClick={() => removeClip(clip.id)}>
            删除片段
          </button>
        </section>
      </div>
    </div>
  );
};
