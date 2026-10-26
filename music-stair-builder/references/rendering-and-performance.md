# 渲染与性能

作者 hoverwu · 版本 0.1.0

这个项目的性能瓶颈不是三角形数量，而是 **draw call 与逐对象材质**。320 块木琴加 319 段导轨如果每块一个 Mesh、每段两根 Tube，会轻松超过 1500 次 draw call，集显只能跑个位数帧率。下面是已经实测有效的做法。

## 1. 场景构成

一套“云海星空”氛围，层次从远到近：

1. **天穹**：大球体内表面 + 垂直渐变着色器，或用 `scene.background` 渐变纹理。
2. **星空**：`THREE.Points`，800 左右，缓慢自转。
3. **远山**：低多边形环形山体，雾色叠加。
4. **云海**：20 个半透明软精灵绕中心缓慢漂移，各自不同半径、相位、速度。
5. **尘埃**：300 个上升粒子，越界回到底部。
6. **阶梯**：主体，见下。
7. **小球**：玻璃球 + 拖尾 + 旋转光点。
8. **特效**：命中环、粒子爆发、选中环、悬停环。

雾用 `FogExp2(0x182349, 0.0075)`，色调映射 `ACESFilmicToneMapping`，曝光 1.08，输出 `SRGBColorSpace`。相机 47° 视场，近裁 0.06，远裁 900。

雾和远山不是装饰：它们遮住长曲螺旋的尽头，让“无限盘旋”的观感成立，同时允许相机用较近距离。

## 2. 普通布局（≤120 块）

每块一个 `Group`：

- `RoundedBoxGeometry` 板体，`MeshPhysicalMaterial`，按音色给不同透射/粗糙度。
- 板前一条发光片，加法混合。
- 地面光晕平面，软纹理。
- 两条细腿 + 两个脚球（可省）。
- 字精灵：`Sprite` + 画布纹理，`depthWrite:false`，`renderOrder:5`。
- 不可见的拾取盒：比板略大，射线检测用。

文字纹理按 `color|lyric|midi|type` 缓存。修改字或颜色时只重建这一块的纹理，并 `dispose()` 旧纹理；不要每帧重画。

命中特效池化：圆环和粒子爆发创建一次，隐藏复用；不要每次命中 `new Mesh`。

## 3. 长布局（>120 块）

`setLayout` 时判定 `longLayout = pads.length > 120`，切换三套策略：

### 板体实例化

按 `type|color` 分组，每组一个 `InstancedMesh`：

```js
const key = `${pad.type}|${pad.color}`;
const mesh = new THREE.InstancedMesh(
  new THREE.BoxGeometry(1, PAD_THICKNESS, 1),
  new THREE.MeshStandardMaterial(boardMaterialPreset(type, color)),
  count
);
// 每个实例：position / Euler(YXZ) / scale(w,1,d)
```

注意：

- 几何体用单位盒，尺寸靠实例矩阵缩放。
- 材质用去掉了 `clearcoat/transmission` 的简化版；物理材质在 300 个实例上很贵。
- 改一块的尺寸/位置时只 `setMatrixAt` 并标 `instanceMatrix.needsUpdate`，不要重建整批。
- 改一块的 `type` 或 `color` 会破坏分组，才需要整批重建。
- 仍然保留每块的 `Group` 用于字精灵、光晕和拾取盒；只把“板体 Mesh”替换成实例。

实例化省掉的是几百个板体的 draw call，不是字精灵。字精灵才是长曲的主要开销。

### 导轨合并

每段导轨生成两段低分段 Tube（主线 10 段、光晕 10 段），全部收集后用：

```js
import { mergeGeometries } from 'three/addons/utils/BufferGeometryUtils.js';
const railGeo = mergeGeometries(railGeos, false);
const glowGeo = mergeGeometries(glowGeos, false);
```

合并成两个 Mesh。珠子用单个 `InstancedMesh`，每段 6 颗，颜色用 `setColorAt`。

普通布局则每段独立 Tube（主线 76 段、光晕 76 段），低配 44 段，每段 14 颗珠子。视觉更细腻，因为数量少。

### 字精灵做 LOD

- 低配（窗口宽 < 720）：字精灵贴图 128×96，最多显示当前段附近 ±12 块的字。
- 高配：贴图 256×192，附近 ±24 块。
- 远景块可以隐藏字精灵，只留发光板。`lyric.visible` 由相机距离或 `u` 决定。

如果仍不够，把相邻同色同字的精灵合并成图集，或改成 `InstancedMesh + 动态纹理数组`。参考实现没有走到这一步，因为 320 块在集显上已经可接受。

## 4. 实测数据与判定

测试机：Intel UHD Graphics 630，1440×900 左右视口，320 块长曲。

- 初次进入 3 秒内偶有 9–12 FPS 的预热帧。
- 预热后三次 1 秒采样：26.8 / 23.9 / 26.8 FPS。
- 同一场景在独立显卡上通常 50–60 FPS。

因此：

- 低配验收阈值用 **>20 FPS**，不要用 60。
- FPS 采样必须“窗口聚焦 + 预热 + 取多次最好值”，否则后台标签页或遮挡会给出假低值。
- 不要用单帧 `dt` 判定性能；用 1 秒内 rAF 计数。

测量代码：

```js
await page.bring_to_front();
await page.waitForTimeout(800);
const fps = await page.evaluate(() => new Promise((resolve) => {
  let n = 0;
  const t0 = performance.now();
  const tick = () => {
    n += 1;
    if (performance.now() - t0 > 1000) resolve(n);
    else requestAnimationFrame(tick);
  };
  requestAnimationFrame(tick);
}));
```

连续测三次取最大值。若三次都低于阈值，再考虑降 DPR、减字精灵、降 Tube 段数。

## 5. 像素比与画质

```js
quality = innerWidth < 720 ? 'low' : 'high';
pixelRatio = min(devicePixelRatio, quality === 'low' ? 1.5 : 1.8);
```

为什么封顶：

- 4K 屏 `devicePixelRatio = 2` 时，渲染像素是 CSS 像素的 4 倍；320 块场景会直接压垮集显。
- 1.8 已经足够锐利，1.5 在手机上肉眼差异很小。

窗口跨过 720px 时重新计算 `quality` 与 DPR，并触发一次 `resize()`。宽高比变化超过 `|ln(aspect/new)| > 0.28` 时重新取景，避免手机横竖屏后场景跑出画面。

## 6. 相机

两个模式：

### 编排视角（orbit）

- `focus` 取所有块包围盒中心。
- `distance` 按竖直/水平视场角分别求适配距离，取较大者再乘 1.12，夹在 18–130。
- `phi = 1.04`（略高于水平），`theta = 0.78`。
- 相机位置 = 球坐标；每帧向目标位置阻尼插值：

```js
const damp = 1 - Math.exp(-dt * 7.5);
camera.position.lerp(target, damp);
camLook.lerp(focus, damp);
camera.lookAt(camLook);
```

### 跟随视角（play）

以小球为中心，沿切线后方 1.8、外侧 6.2、上方 4.4：

```js
followPos = ballPos
  - flatTangent * 1.8
  + outward * 6.2;
followPos.y = ballPos.y + 4.4;

followLook = ballPos + flatTangent * 1.8;
followLook.y = ballPos.y + 0.5;
```

两套阻尼分别取 3.1 与 4.2，让相机略滞后于球，产生速度感。切线水平投影长度过小时退回 `(0,0,1)`，避免俯冲段相机翻转。

切换模式时不要瞬移：`world.setFollowing(true/false)` 只改标志，位置仍走 lerp。

### 交互

- 拖拽：`theta -= dx*0.0052`，`phi = clamp(phi - dy*0.0042, 0.16, 1.47)`。
- 滚轮：`distance *= exp(delta)`，夹在 6.5–95。
- 双击块：`focusPad(index, 13)`，聚焦到块上方并稍微侧转。
- 拖拽块时把屏幕坐标投到一条水平面，得到世界坐标；不要用相机平面，否则斜视角下会漂。

## 7. 命中特效

- **板闪光**：`flash` 从 1 衰减到 0，驱动 `emissiveIntensity`、字精灵缩放（1.05 → 1.23 → 1.05）与颜色变亮。
- **命中环**：预创建 8 个圆环，命中时放到块上，`life` 0→1，缩放 1.1→4.3，透明度 0.85→0。
- **粒子爆发**：一次 28–40 个点，带初速度与重力，0.75 秒寿命；位置属性每帧更新，`needsUpdate`。
- **小球脉冲**：命中时 `ballPulse=1`，缩放 `1 + sin(pulse*PI)*0.16`。
- **选中环**：透明度 `0.6 + sin(t*3.2)*0.25`，只对选中块显示。

所有特效对象复用，超出寿命只隐藏不销毁。`update(dt)` 中跳过 `life >= 1` 的对象，避免无意义计算。

## 8. 拾取与拖拽

- 拾取用不可见盒做 `Raycaster.intersectObjects(pickMeshes, false)`，不要对实例化板体直接射线检测（实例需要额外转换）。
- 拾取盒略大于板体：`w+0.25, 0.6, d+0.3`，手机上更好点。
- 拖拽时禁用相机旋转；用一个状态机区分 `orbit | dragPad | dragHandle`。
- 拖动块的 y 值要限制在合理范围（参考实现 ±28/22），防止拖到雾外找不到。

## 9. 移动端

- 390px 宽必须无横向溢出。重点检查：待转换卡片、编辑器滑杆行、播放条、曲库标签。
- 滑杆标签加 `white-space: nowrap`，否则“飞行时间”会折成两行把布局撑高。
- 编辑器面板改为底部抽屉，最大高度 `70vh`，内部滚动；不要整页滚动。
- 触控目标 ≥ 40px；拖拽块与旋转相机的手势要分开（单指拖块，双指/空白处旋转）。
- `quality='low'` 时减少星空、云、尘埃数量与 Tube 段数。
- 竖屏时取景距离要按更小的水平视场重新计算，否则阶梯左右会被裁掉。

## 10. 资源释放

`setLayout` 会清空 `padRoot` 与 `railRoot`。清理函数必须：

```js
object.traverse((o) => {
  o.geometry?.dispose();
  const mats = Array.isArray(o.material) ? o.material : o.material ? [o.material] : [];
  mats.forEach((m) => {
    if (m.userData?.ownTexture && m.map) m.map.dispose();
    m.dispose();
  });
});
```

字精灵的纹理是本块独有的，标记 `ownTexture = true` 后才释放；共享的软光晕纹理不要重复释放。切歌、切变体、插入/删除都会走这条路径，漏释放会在几十次切换后耗尽显存。

## 11. 性能排查顺序

1. 打开渲染器信息：`renderer.info.render.calls / triangles`。
2. draw call 是否随块数线性增长？是 → 板体没实例化或导轨没合并。
3. 材质数量是否等于块数？是 → 没有按 `type|color` 复用。
4. 字精灵是否每块一张纹理？是 → 检查纹理缓存键。
5. DPR 是否被系统缩放推到 3 以上？是 → 封顶。
6. 是否每帧重建几何/材质？用 Chrome Performance 看 GC 与 `compile` 峰值。
7. 以上都正常但仍低 → 降低 Tube 段数、粒子数、隐藏远景字精灵。

按这个顺序，通常在第 2 或第 3 步就能找到主因。
