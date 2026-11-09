import {d as defineComponent,u as useApp,j as ref,s as computed,a as h,l as rpc} from "./index-CVDv6sjN.js";
import {_ as VideoPreview} from "./VideoPreview.vue_vue_type_script_setup_true_lang-Dj2z1xV5.js";
import TimelineEditor from './TimelineEditor.js';

const VIDEO_FILTER = "视频素材|*.mp4;*.mov;*.mkv;*.avi;*.webm;*.m4v;*.mts|所有文件|*.*";
const ACTIVE = ["queued", "running", "paused", "cancelling"];
const STYLE = `
.video-tools-page{gap:0}.vt-grid{display:grid;grid-template-columns:minmax(0,1.15fr) minmax(290px,.85fr);gap:18px;align-items:start}.vt-column{display:grid;gap:18px}.vt-panel h2{margin:0 0 12px}.vt-meta{color:var(--color-text-secondary);font-size:12px;overflow-wrap:anywhere}.vt-stage{position:relative;max-width:100%;margin:14px auto;background:#111827;outline:1px solid var(--color-border);overflow:hidden;touch-action:none;cursor:crosshair;user-select:none}.vt-stage img{display:block;width:100%;height:100%;pointer-events:none}.vt-selection{position:absolute;border:2px solid #4b9cff;background:#4b9cff28;box-sizing:border-box;pointer-events:none}.vt-coordinates{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px}.vt-field{display:grid;gap:6px;margin:12px 0}.vt-field input{min-width:0;width:100%;box-sizing:border-box}.vt-clip{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:12px 0;border-bottom:1px solid var(--color-border)}.vt-clip:last-child{border-bottom:0}.vt-clip-info{min-width:0;overflow-wrap:anywhere}.vt-clip-info strong{display:block}.vt-clip .actions{flex-shrink:0}.vt-help{font-size:12px;color:var(--color-text-secondary);line-height:1.7}.vt-error{border:1px solid var(--color-danger);border-radius:8px;padding:12px;margin-bottom:16px;color:var(--color-danger);white-space:pre-line;overflow-wrap:anywhere}.vt-output{overflow-wrap:anywhere}.vt-task{padding:12px 0;border-bottom:1px solid var(--color-border)}.vt-task progress{width:100%;margin:8px 0}.vt-task .between{flex-wrap:wrap}.vt-empty{padding:20px 0;color:var(--color-text-secondary)}.vt-result .video-preview{margin-top:12px}.vt-output-actions{margin-top:16px}.vt-tab-count{font-size:12px;color:var(--color-text-secondary)}
@media(max-width:980px){.vt-grid{grid-template-columns:1fr}.vt-clip{flex-wrap:wrap}}@media(max-width:580px){.vt-coordinates{grid-template-columns:repeat(2,minmax(0,1fr))}.vt-clip .actions{width:100%}}
.video-tools-page.vt-timeline-mode{padding:18px 24px!important}.vt-timeline-mode>.page-header{margin:0 0 6px;align-items:center}.vt-timeline-mode>.page-header h1{font-size:24px;line-height:1.2;margin:0}.vt-timeline-mode>.page-header p{font-size:12px;margin:6px 0 0}.vt-timeline-mode>.subnav{margin:10px 0 8px!important;padding:0;min-height:38px;gap:22px}.vt-timeline-mode>.subnav button{padding:9px 0}
@media(max-width:1440px){.video-tools-page.vt-timeline-mode{padding:16px 20px!important}}
`;

const VideoTools = defineComponent({
  name: "VideoTools",
  setup() {
    const store = useApp();
    const tab = ref("timeline");
    const source = ref(null);
    const clips = ref([]);
    const rect = ref({x: 0, y: 0, width: 0, height: 0});
    const outputFolder = ref("");
    const names = ref({watermark: "去水印.mp4", concat: "视频拼接.mp4"});
    const outputs = ref({watermark: "", concat: ""});
    const loading = ref(false);
    const busy = ref(false);
    const timelineBusy = ref(false);
    const error = ref("");
    const cancelPending = ref({});
    let clipKey = 0;
    let drag = null;

    const validRect = computed(() => {
      const video = source.value, area = rect.value;
      return !!video && [area.x, area.y, area.width, area.height].every(Number.isInteger)
        && area.x >= 0 && area.y >= 0 && area.width >= 2 && area.height >= 2
        && area.x + area.width <= video.width && area.y + area.height <= video.height;
    });
    const tasks = computed(() => (store.tasks || []).filter(task => task.location?.route === "/video-tools").slice(0, 5));

    function basename(path) {
      return String(path).split(/[\\/]/).pop() || String(path);
    }
    function message(reason) {
      return reason instanceof Error ? reason.message : String(reason || "处理失败，请重试");
    }
    function info(video) {
      return `${video.width} × ${video.height} · ${Number(video.duration).toFixed(1)} 秒 · ${video.hasAudio ? "有音频" : "无音频"}`;
    }
    function setTab(next) {
      if (busy.value || loading.value || timelineBusy.value) return;
      tab.value = next;
      error.value = "";
    }
    async function probe(path) {
      const video = await rpc.invoke("video.probe", {path});
      if (!video || !Number.isInteger(video.width) || video.width <= 0
        || !Number.isInteger(video.height) || video.height <= 0
        || !Number.isFinite(video.duration) || video.duration <= 0
        || typeof video.path !== "string" || !video.path
        || typeof video.preview !== "string" || !video.preview.startsWith("data:image/")) {
        throw new Error("无法读取视频信息，请重新选择视频");
      }
      return video;
    }
    async function selectSource() {
      if (busy.value || loading.value) return;
      loading.value = true;
      error.value = "";
      try {
        const paths = await rpc.invoke("file.select", {multiple: false, filter: VIDEO_FILTER});
        if (!paths?.[0]) return;
        source.value = null;
        rect.value = {x: 0, y: 0, width: 0, height: 0};
        outputs.value.watermark = "";
        drag = null;
        source.value = await probe(paths[0]);
        names.value.watermark = "去水印_" + basename(source.value.path).replace(/\.[^.]+$/, "") + ".mp4";
      } catch (reason) {
        error.value = message(reason);
      } finally {
        loading.value = false;
      }
    }
    async function addClips() {
      if (busy.value || loading.value) return;
      loading.value = true;
      error.value = "";
      try {
        const paths = await rpc.invoke("file.select", {multiple: true, filter: VIDEO_FILTER});
        const failures = [];
        for (const path of paths || []) {
          try {
            clips.value.push({...await probe(path), key: ++clipKey});
            outputs.value.concat = "";
          } catch (reason) {
            failures.push(basename(path) + "：" + message(reason));
          }
        }
        error.value = failures.join("\n");
      } catch (reason) {
        error.value = message(reason);
      } finally {
        loading.value = false;
      }
    }
    function moveClip(index, delta) {
      if (busy.value || loading.value) return;
      const target = index + delta;
      if (target < 0 || target >= clips.value.length) return;
      const moved = clips.value.splice(index, 1)[0];
      clips.value.splice(target, 0, moved);
      outputs.value.concat = "";
    }
    function removeClip(index) {
      if (busy.value || loading.value) return;
      clips.value.splice(index, 1);
      outputs.value.concat = "";
    }
    async function selectOutput() {
      if (busy.value || loading.value) return;
      loading.value = true;
      error.value = "";
      try {
        const folder = await rpc.invoke("folder.select");
        if (folder) outputFolder.value = folder;
      } catch (reason) {
        error.value = message(reason);
      } finally {
        loading.value = false;
      }
    }
    function outputPath() {
      if (!outputFolder.value) throw new Error("请先选择输出文件夹");
      const name = names.value[tab.value].trim();
      if (!name || /[<>:"/\\|?*\u0000-\u001f]/.test(name) || !/\.mp4$/i.test(name)
        || /^(con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\.|$)/i.test(name)) {
        throw new Error("请输入有效的 MP4 文件名；文件名不能包含路径或特殊字符");
      }
      return outputFolder.value.replace(/[\\/]+$/, "") + "\\" + name;
    }
    async function start() {
      if (busy.value || loading.value) return;
      error.value = "";
      const mode = tab.value;
      try {
        if (mode === "watermark" && !validRect.value) throw new Error("请框选有效区域，区域必须位于视频画面内");
        if (mode === "concat" && clips.value.length < 2) throw new Error("请至少添加两段视频");
        const output = outputPath();
        const data = mode === "watermark"
          ? {path: source.value.path, output, rect: {...rect.value}}
          : {paths: clips.value.map(video => video.path), output};
        busy.value = true;
        outputs.value[mode] = "";
        const result = await store.runJob(mode === "watermark" ? "video.removeWatermark" : "video.concat", data);
        if (typeof result?.path !== "string" || !result.path) throw new Error("任务已结束，但未返回输出文件路径，请查看任务中心");
        outputs.value[mode] = result.path;
      } catch (reason) {
        error.value = message(reason);
      } finally {
        busy.value = false;
      }
    }
    function point(event) {
      const bounds = event.currentTarget.getBoundingClientRect();
      if (!source.value || !bounds.width || !bounds.height) return null;
      return {
        x: Math.max(0, Math.min(source.value.width, Math.round((event.clientX - bounds.left) / bounds.width * source.value.width))),
        y: Math.max(0, Math.min(source.value.height, Math.round((event.clientY - bounds.top) / bounds.height * source.value.height)))
      };
    }
    function dragStart(event) {
      if (busy.value || loading.value || event.button !== 0) return;
      const origin = point(event);
      if (!origin) return;
      event.preventDefault();
      drag = {...origin, pointerId: event.pointerId};
      event.currentTarget.setPointerCapture?.(event.pointerId);
      rect.value = {...origin, width: 0, height: 0};
      error.value = "";
    }
    function dragMove(event) {
      if (!drag || event.pointerId !== drag.pointerId) return;
      const end = point(event);
      if (!end) return;
      rect.value = {x: Math.min(drag.x, end.x), y: Math.min(drag.y, end.y), width: Math.abs(end.x - drag.x), height: Math.abs(end.y - drag.y)};
    }
    function dragEnd(event) {
      if (!drag || event.pointerId !== drag.pointerId) return;
      dragMove(event);
      event.currentTarget.releasePointerCapture?.(event.pointerId);
      drag = null;
    }
    function setCoordinate(key, event) {
      const value = event.target.value;
      rect.value = {...rect.value, [key]: value === "" ? null : Math.round(Number(value))};
    }
    async function cancel(task) {
      if (cancelPending.value[task.taskId] || !ACTIVE.includes(task.status) || task.status === "cancelling") return;
      cancelPending.value[task.taskId] = true;
      try {
        await rpc.invoke("task.cancel", {taskId: task.taskId});
      } catch (reason) {
        delete cancelPending.value[task.taskId];
        error.value = message(reason);
      }
    }
    async function reveal(path) {
      try {
        await rpc.invoke("file.reveal", {path});
      } catch (reason) {
        error.value = message(reason);
      }
    }

    return () => {
      const disabled = busy.value || loading.value || timelineBusy.value;
      const video = source.value;
      const mode = tab.value;
      const output = outputs.value[mode];
      const coordinate = (key, label, maximum) => h("label", {class: "vt-field"}, [
        h("span", null, label),
        h("input", {id: "video-watermark-" + key, type: "number", min: key === "x" || key === "y" ? 0 : 2, max: maximum, step: 1,
          value: rect.value[key], disabled, onInput: event => setCoordinate(key, event)})
      ]);
      const clipRows = clips.value.map((clip, index) => h("div", {key: clip.key, class: "vt-clip"}, [
        h("div", {class: "vt-clip-info"}, [h("strong", null, `${index + 1}. ${basename(clip.path)}`), h("p", {class: "vt-meta"}, info(clip)), h("small", {title: clip.path}, clip.path)]),
        h("div", {class: "actions"}, [
          h("button", {disabled: disabled || index === 0, "aria-label": `上移第 ${index + 1} 段`, onClick: () => moveClip(index, -1)}, "上移"),
          h("button", {disabled: disabled || index === clips.value.length - 1, "aria-label": `下移第 ${index + 1} 段`, onClick: () => moveClip(index, 1)}, "下移"),
          h("button", {disabled, "aria-label": `移除第 ${index + 1} 段`, onClick: () => removeClip(index)}, "移除")
        ])
      ]));
      const watermarkPanel = h("article", {class: "panel vt-panel"}, [
        h("div", {class: "between"}, [h("h2", null, "框选水印区域"), h("button", {disabled, onClick: selectSource}, "选择视频")]),
        video ? h("div", null, [
          h("p", {class: "vt-meta"}, basename(video.path) + " · " + info(video)),
          h("div", {id: "video-watermark-stage", class: "vt-stage", role: "group", "aria-label": "拖动框选固定水印区域",
            style: {aspectRatio: `${video.width}/${video.height}`, width: `min(100%, ${Math.round(420 * video.width / video.height)}px)`},
            onPointerdown: dragStart, onPointermove: dragMove, onPointerup: dragEnd, onPointercancel: () => {drag = null;}}, [
            h("img", {src: video.preview, alt: "视频画面预览，拖动框选水印区域", draggable: false,
              onError: () => {error.value = "预览图片无法显示，请重新选择视频；也可按像素坐标指定区域";}}),
            validRect.value ? h("div", {class: "vt-selection", style: {left: `${rect.value.x / video.width * 100}%`, top: `${rect.value.y / video.height * 100}%`, width: `${rect.value.width / video.width * 100}%`, height: `${rect.value.height / video.height * 100}%`}}) : null
          ]),
          h("div", {class: "vt-coordinates"}, [coordinate("x", "左侧 X（像素）", video.width - 1), coordinate("y", "顶部 Y（像素）", video.height - 1), coordinate("width", "区域宽度", video.width), coordinate("height", "区域高度", video.height)]),
          h("p", {class: "vt-help"}, validRect.value ? "区域坐标对应预览画面，可直接调整数值。" : "在画面上拖动框选区域，或填写像素坐标；区域至少为 2 × 2 像素。")
        ]) : h("p", {class: "vt-empty"}, loading.value ? "正在读取视频…" : "选择本地视频后，在预览画面上拖动框选固定位置的水印。"),
        h("p", {class: "vt-help"}, "使用周围画面修复固定区域并保留音频。复杂背景可能留下模糊痕迹，无法恢复被水印遮挡的原始细节。")
      ]);
      const concatPanel = h("article", {class: "panel vt-panel"}, [
        h("div", {class: "between"}, [h("h2", null, "按顺序拼接"), h("button", {disabled, onClick: addClips}, "添加视频")]),
        clips.value.length ? h("div", null, clipRows) : h("p", {class: "vt-empty"}, loading.value ? "正在读取视频…" : "至少添加两段视频，按从上到下的顺序拼接。"),
        h("p", {class: "vt-help"}, "按第一段视频确定画布，各段保持原比例；不同尺寸通过补边适配。统一帧率与音频格式，无声片段补静音，有声片段保留声音。")
      ]);
      return h("section", {class: "page video-tools-page"+(mode==='timeline'?' vt-timeline-mode':'')}, [
        h("style", null, STYLE),
        h("header", {class: "page-header"}, [h("div", null, [h("h1", null, "视频工具"), h("p", null, "在时间线上编排画面、文字和声音，预览后导出成片。")]), h("button", {onClick: () => {store.taskCenterOpen = true;}}, "打开任务中心")]),
        h("nav", {class: "subnav", "aria-label": "视频工具功能"}, [
          h("button", {id:'video-tools-timeline-tab',class:mode==='timeline'?'active':'',disabled,"aria-pressed":mode==='timeline',onClick:()=>setTab('timeline')},'时间线剪辑'),
          h("button", {class: mode === "watermark" ? "active" : "", disabled, "aria-pressed": mode === "watermark", onClick: () => setTab("watermark")}, "消除水印"),
          h("button", {class: mode === "concat" ? "active" : "", disabled, "aria-pressed": mode === "concat", onClick: () => setTab("concat")}, "视频拼接")
        ]),
        error.value ? h("p", {class: "vt-error", role: "alert"}, error.value) : null,
        mode==='timeline'?h(TimelineEditor,{active:true,onBusy:value=>timelineBusy.value=!!value}):h("div", {class: "vt-grid"}, [h("div", {class: "vt-column"}, [mode === "watermark" ? watermarkPanel : concatPanel]),
          h("div", {class: "vt-column"}, [
            h("article", {class: "panel vt-panel"}, [
              h("h2", null, "输出视频"),
              h("label", {class: "vt-field"}, [h("span", null, "输出文件夹"), h("input", {id: "video-output-folder", value: outputFolder.value, placeholder: "请选择输出文件夹", readonly: true, title: outputFolder.value}), h("button", {disabled, onClick: selectOutput}, "选择输出文件夹")]),
              h("label", {class: "vt-field"}, [h("span", null, "MP4 文件名"), h("input", {id: "video-output-name", value: names.value[mode], disabled, onInput: event => {names.value[mode] = event.target.value;}})]),
              h("p", {class: "vt-help"}, "输出保存为新文件。原视频保持完整；若同名文件已存在，请更换名称。"),
              h("div", {class: "actions vt-output-actions"}, [h("button", {class: "primary", disabled: disabled || !outputFolder.value || (mode === "watermark" ? !validRect.value : clips.value.length < 2), onClick: start}, busy.value ? "处理中…" : mode === "watermark" ? "开始消除水印" : "开始拼接")])
            ]),
            tasks.value.length ? h("article", {class: "panel vt-panel", "aria-label": "视频任务进度"}, [h("h2", null, "任务进度"), ...tasks.value.map(task => h("div", {key: task.taskId, class: "vt-task"}, [
              h("div", {class: "between"}, [h("strong", null, task.name), h("span", {class: "vt-meta"}, task.status === "done" ? "已完成" : task.status === "cancelled" ? "已取消" : task.status === "failed" ? "失败" : task.status === "paused" ? "已暂停" : task.status === "queued" ? "排队中" : task.status === "cancelling" ? "取消中" : "处理中")]),
              h("p", {class: "vt-meta"}, task.message),
              h("progress", {max: 100, value: Number(task.progress) || 0, "aria-label": task.name + "进度"}),
              h("div", {class: "between"}, [h("span", null, (Number(task.progress) || 0) + "%"), ACTIVE.includes(task.status) ? h("button", {disabled: task.status === "cancelling" || !!cancelPending.value[task.taskId], onClick: () => cancel(task)}, task.status === "cancelling" || cancelPending.value[task.taskId] ? "取消中…" : "取消任务") : null]),
              task.status === "done" && task.result?.path ? h("div", {class: "vt-output"}, [
                h("p", {class: "vt-meta"}, task.result.path),
                h("div", {class: "actions"}, [h("button", {onClick: () => {outputs.value[mode] = task.result.path;}}, "预览结果"), h("button", {onClick: () => reveal(task.result.path)}, "打开文件位置")])
              ]) : null,
              task.error ? h("p", {class: "error-text"}, task.error) : null
            ]))]) : null,
            output ? h("article", {class: "panel vt-panel vt-result"}, [h("h2", null, "处理完成"), h("p", {class: "vt-output"}, output), h("button", {onClick: () => reveal(output)}, "打开文件位置"), h(VideoPreview, {path: output})]) : null
          ])
        ])
      ]);
    };
  }
});

export default VideoTools;
