// ─────────────────────────────────────────────────────────────────────────────
// 项目：VoiceSystem
// 文件：ConfigService.cs
// 作者：Maddie
// 日期：2025年04月23日
// ─────────────────────────────────────────────────────────────────────────────
// 说明：提供统一的配置访问服务，支持读取、修改、保存 INI 格式的配置项，内部使用线程安全字典存储数据。
// ─────────────────────────────────────────────────────────────────────────────


// VoiceSystem/Config/ConfigService.cs
using System.Collections.Generic;
using System.Threading.Tasks;
using UnityEngine;

public static class ConfigService
{
    // 线程锁对象
    static readonly object _Lock = new();

    // 配置数据字典（节 -> 键值）
    static Dictionary<string, Dictionary<string, string>> _Data;

    // 是否已初始化
    public static bool _Loaded = false;

    /// <summary>
    /// 初始化配置服务（在应用启动时调用）
    /// </summary>
    public static async Task InitAsync()
    {
        if (_Loaded) return;

        await ConfigPath.EnsureFileAsync();
        _Data = IniParser.Read(ConfigPath.WritablePath);
        _Loaded = true;
    }

    /// <summary>
    /// 获取配置项的值
    /// </summary>
    /// <param name="_Section">节名称</param>
    /// <param name="_Key">键名</param>
    /// <param name="_Default">默认值（未找到时返回）</param>
    /// <returns>配置项的值</returns>
    public static string Get(string _Section, string _Key, string _Default = "")
    {
        if (!_Loaded)
        {
            Debug.LogError("[ConfigService] 尚未初始化，返回默认值");
            return _Default;
        }

        return _Data.TryGetValue(_Section, out var _Sec) && _Sec.TryGetValue(_Key, out var _Val)
            ? _Val : _Default;
    }

    /// <summary>
    /// 设置配置项的值
    /// </summary>
    /// <param name="_Section">节名称</param>
    /// <param name="_Key">键名</param>
    /// <param name="_Value">要设置的值</param>
    /// <param name="_SaveImmediately">是否立即保存到磁盘</param>
    public static void Set(string _Section, string _Key, string _Value, bool _SaveImmediately = true)
    {
        lock (_Lock)
        {
            if (!_Data.ContainsKey(_Section))
                _Data[_Section] = new Dictionary<string, string>();

            _Data[_Section][_Key] = _Value;

            if (_SaveImmediately)
                Save();
        }
    }

    /// <summary>
    /// 保存配置到磁盘
    /// </summary>
    public static void Save()
    {
        IniParser.Write(ConfigPath.WritablePath, _Data);
        Debug.Log("[ConfigService] 配置已保存");
    }
}
