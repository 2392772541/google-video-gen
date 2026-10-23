(() => {
  'use strict';
  document.addEventListener('DOMContentLoaded', () => {
    const iframe = document.getElementById('canvas-iframe');
    const refreshBtn = document.getElementById('btn-refresh-canvas');
    const drawerBtn = document.getElementById('btn-toggle-media-drawer');
    const drawer = document.getElementById('canvas-media-drawer');
    const drawerList = document.getElementById('drawer-media-list');
    const importBtn = document.getElementById('btn-import-canvas-local');
    const fileInput = document.getElementById('canvas-import-file-input');
    const importAlert = document.getElementById('canvas-import-alert');
    const statusPill = document.getElementById('canvas-status-pill');
    const proxyPill = document.getElementById('proxy-status-pill');
    const cpaPill = document.getElementById('cpa-status-pill');

    function showToast(msg, isSuccess = true) {
      if (!importAlert) return;
      importAlert.textContent = msg;
      importAlert.style.display = 'block';
      importAlert.style.background = isSuccess ? 'rgba(16,185,129,0.15)' : 'rgba(239,68,68,0.15)';
      importAlert.style.color = isSuccess ? '#34d399' : '#f87171';
      setTimeout(() => {
        importAlert.style.display = 'none';
      }, 3500);
    }

    if (importBtn && fileInput) {
      importBtn.addEventListener('click', () => {
        fileInput.click();
      });
      fileInput.addEventListener('change', async (e) => {
        const file = e.target.files && e.target.files[0];
        if (!file) return;
        const reader = new FileReader();
        reader.onload = async () => {
          const dataUrl = reader.result;
          const isVid = file.type.startsWith('video/');
          try {
            const res = await fetch('/api/canvas/import-to-farm', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({
                data_url: dataUrl,
                media_type: isVid ? 'video' : 'image',
                prompt: file.name
              })
            });
            if (!res.ok) {
              const err = await res.json();
              throw new Error(err.detail || '导入失败');
            }
            showToast(`已成功将「${file.name}」导入视频工坊！`);
            loadRecentMedia();
          } catch (err) {
            showToast('导入失败: ' + err.message, false);
          } finally {
            fileInput.value = '';
          }
        };
        reader.readAsDataURL(file);
      });
    }

    window.addEventListener('message', async (e) => {
      if (!e.data || typeof e.data !== 'object') return;
      if (e.data.type === 'CANVAS_EXPORT_TO_FARM') {
        try {
          const payload = e.data.payload || {};
          const res = await fetch('/api/canvas/import-to-farm', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              data_url: payload.dataUrl,
              url: payload.url,
              media_type: payload.mediaType || 'image',
              prompt: payload.title || '画布生成素材'
            })
          });
          if (!res.ok) throw new Error('HTTP ' + res.status);
          showToast('已从无限画布接收并存入工坊！');
          loadRecentMedia();
        } catch (err) {
          console.error('Failed to import canvas payload:', err);
          showToast('接收画布导出失败: ' + err.message, false);
        }
      }
    });

    if (refreshBtn && iframe) {
      refreshBtn.addEventListener('click', () => {
        try {
          iframe.src = iframe.src;
        } catch (e) {
          iframe.src = 'http://127.0.0.1:3000/?baseUrl=http://127.0.0.1:8317/v1&apiKey=sk-local-23fa8d80e597d0c0d90c2e75d1c1430787ed13afe1175d70';
        }
      });
    }

    if (drawerBtn && drawer) {
      drawerBtn.addEventListener('click', () => {
        const isOpen = drawer.classList.toggle('open');
        drawerBtn.setAttribute('aria-expanded', String(isOpen));
        if (isOpen) {
          loadRecentMedia();
        }
      });
    }

    async function checkStatus() {
      try {
        const res = await fetch('/api/canvas/status');
        if (!res.ok) return;
        const data = await res.json();
        if (statusPill) {
          statusPill.textContent = data.canvas_app ? '● 画布 3000 在线' : '○ 画布 3000 离线';
          statusPill.className = 'pill status-pill ' + (data.canvas_app ? 'online' : 'offline');
        }
        if (proxyPill) {
          proxyPill.textContent = data.canvas_proxy ? '● 代理 23210 就绪' : '○ 代理 23210 未启动';
          proxyPill.className = 'pill status-pill ' + (data.canvas_proxy ? 'online' : 'offline');
        }
        if (cpaPill) {
          cpaPill.textContent = data.cliproxyapi ? `● 8317 (${data.models_count || 0}模型)` : '○ 8317 离线';
          cpaPill.className = 'pill status-pill ' + (data.cliproxyapi ? 'online' : 'offline');
        }
      } catch (err) {
        console.warn('Canvas status check failed:', err);
      }
    }

    async function loadRecentMedia() {
      if (!drawerList) return;
      drawerList.innerHTML = '<div style="padding:12px;color:var(--text-muted);font-size:12px;">正在加载视频工坊素材...</div>';
      try {
        const res = await fetch('/api/canvas/recent-media');
        if (!res.ok) throw new Error('HTTP ' + res.status);
        const items = await res.json();
        if (!items || items.length === 0) {
          drawerList.innerHTML = '<div style="padding:12px;color:var(--text-muted);font-size:12px;">暂无可用成片或素材</div>';
          return;
        }
        drawerList.innerHTML = '';
        items.forEach(item => {
          const card = document.createElement('div');
          card.className = 'drawer-media-card';
          const isVideo = item.type === 'video';
          const mediaEl = isVideo
            ? `<video src="${item.url}" preload="metadata" muted style="width:100%;height:84px;object-fit:cover;border-radius:4px;background:#000;"></video>`
            : `<img src="${item.url}" alt="${item.name || ''}" style="width:100%;height:84px;object-fit:cover;border-radius:4px;background:#111;"/>`;
          
          card.innerHTML = `
            ${mediaEl}
            <div class="card-meta" style="margin-top:6px;">
              <div style="font-size:12px;font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;" title="${item.name}">${item.name}</div>
              <div style="font-size:11px;color:var(--text-muted);margin-top:2px;">${item.size_desc || ''} · ${item.time_desc || ''}</div>
              <div style="display:flex;gap:4px;margin-top:6px;">
                <button class="btn btn-xs btn-secondary btn-copy-url" data-url="${item.url}" style="font-size:11px;padding:2px 6px;">复制地址</button>
                <a href="${item.url}" target="_blank" download class="btn btn-xs btn-secondary" style="font-size:11px;padding:2px 6px;text-decoration:none;">下载</a>
              </div>
            </div>
          `;
          drawerList.appendChild(card);
        });

        drawerList.querySelectorAll('.btn-copy-url').forEach(btn => {
          btn.addEventListener('click', (e) => {
            const targetUrl = new URL(btn.dataset.url, window.location.origin).href;
            navigator.clipboard.writeText(targetUrl).then(() => {
              const oldText = btn.textContent;
              btn.textContent = '已复制!';
              setTimeout(() => { btn.textContent = oldText; }, 1500);
            });
          });
        });
      } catch (err) {
        drawerList.innerHTML = `<div style="padding:12px;color:var(--danger,#f43f5e);font-size:12px;">加载失败: ${err.message}</div>`;
      }
    }

    checkStatus();
  });
})();
