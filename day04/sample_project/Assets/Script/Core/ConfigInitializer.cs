// ─────────────────────────────────────────────────────────────────────────────
// 项目：VoiceSystem
// 文件：ConfigInitializer.cs
// 作者：Maddie
// 日期：2025年04月23日
// ─────────────────────────────────────────────────────────────────────────────
// 说明：Unity启动初始化器，在游戏开始时确保配置服务加载完毕，并可设置该对象在场景间持久存在。
// ─────────────────────────────────────────────────────────────────────────────


// VoiceSystem/Config/ConfigInitializer.cs
using UnityEngine;
using System.Threading.Tasks;

[AddComponentMenu("VoiceSystem/Config/Config Initializer")]
public class ConfigInitializer : MonoBehaviour
{
    /// <summary>
    /// Unity生命周期事件：对象创建时初始化配置服务
    /// </summary>
    private async void Awake()
    {
        // 重置标志，确保 InitAsync 生效
        ConfigService._Loaded = false;

        // 异步加载配置
        await ConfigService.InitAsync();

        // 保持对象不被销毁（跨场景复用）
        DontDestroyOnLoad(gameObject);
    }
}
