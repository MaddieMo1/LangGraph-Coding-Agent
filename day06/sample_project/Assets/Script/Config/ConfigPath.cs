// ─────────────────────────────────────────────────────────────────────────────
// 项目：VoiceSystem
// 文件：ConfigPath.cs
// 作者：Maddie
// 日期：2025年04月23日
// ─────────────────────────────────────────────────────────────────────────────
// 说明：用于在首次运行时将 StreamingAssets 中的配置文件复制到可写目录 persistentDataPath，确保配置文件存在且内容最新。
// ─────────────────────────────────────────────────────────────────────────────


// VoiceSystem/Config/ConfigPath.cs
using UnityEngine;
using System.IO;
using System.Threading.Tasks;
using UnityEngine.Networking;

[AddComponentMenu("VoiceSystem/Config/Config Path")]
internal static class ConfigPath
{
    // 配置文件名常量
    public const string FileName = "SoftwareAnswerConfig.ini";

    // 获取配置文件的持久化路径
    public static string WritablePath =>
        Path.Combine(Application.persistentDataPath, FileName);

    /// <summary>
    /// 确保配置文件已复制到可写路径（首次运行时执行）
    /// </summary>
    public static async Task EnsureFileAsync()
    {
        // 源路径
        string _SrcPath = Path.Combine(Application.streamingAssetsPath, FileName);

        // 目标路径
        string _DstPath = WritablePath;

        Debug.Log("准备配置文件：" + _DstPath);

#if UNITY_ANDROID && !UNITY_EDITOR
        using UnityWebRequest _Request = UnityWebRequest.Get(_SrcPath);
        await _Request.SendWebRequest();

        if (_Request.result == UnityWebRequest.Result.Success)
        {
            // 新数据内容
            byte[] _NewData = _Request.downloadHandler.data;

            if (!File.Exists(_DstPath) || !CompareFile(_DstPath, _NewData))
            {
                File.WriteAllBytes(_DstPath, _NewData);
                Debug.Log("[ConfigPath] 已覆盖写入配置文件");
            }
            else
            {
                Debug.Log("[ConfigPath] 配置文件无变化，无需覆盖");
            }
        }
        else
        {
            Debug.LogError($"[ConfigPath] 复制失败: {_Request.error}");
        }
#else
        if (!File.Exists(_SrcPath))
        {
            Debug.LogWarning($"[ConfigPath] 源文件不存在: {_SrcPath}");
            return;
        }

        // 新数据内容
        byte[] _NewData = File.ReadAllBytes(_SrcPath);
        if (!File.Exists(_DstPath) || !CompareFile(_DstPath, _NewData))
        {
            File.WriteAllBytes(_DstPath, _NewData);
            Debug.Log("[ConfigPath] 已覆盖写入配置文件");
        }
        else
        {
            Debug.Log("[ConfigPath] 配置文件无变化，无需覆盖");
        }
        await Task.Yield();
#endif
    }

    /// <summary>
    /// 比较两个文件内容是否一致
    /// </summary>
    /// <param name="_FilePath">已存在的文件路径</param>
    /// <param name="_NewData">新文件数据</param>
    /// <returns>是否完全一致</returns>
    private static bool CompareFile(string _FilePath, byte[] _NewData)
    {
        try
        {
            // 旧数据内容
            byte[] _OldData = File.ReadAllBytes(_FilePath);
            if (_OldData.Length != _NewData.Length) return false;

            for (int i = 0; i < _OldData.Length; i++)
                if (_OldData[i] != _NewData[i]) return false;

            return true;
        }
        catch
        {
            // 读取失败 → 强制刷新
            return false;
        }
    }
}
