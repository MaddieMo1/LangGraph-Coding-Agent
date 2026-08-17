// ─────────────────────────────────────────────────────────────────────────────
// 项目：VoiceSystem
// 文件：IniParser.cs
// 作者：Maddie
// 日期：2025年04月23日
// ─────────────────────────────────────────────────────────────────────────────
// 说明：用于解析 INI 配置文件格式，支持读取和写入操作，结构支持节（Section）和键值（Key-Value）对形式。
// ─────────────────────────────────────────────────────────────────────────────


// VoiceSystem/Config/IniParser.cs
using System.Collections.Generic;
using System.IO;
using System.Text;

internal static class IniParser
{
    /// <summary>
    /// 从指定路径读取 INI 配置文件
    /// </summary>
    /// <param name="_Path">配置文件路径</param>
    /// <returns>返回一个嵌套字典结构：节名 -> (键 -> 值)</returns>
    public static Dictionary<string, Dictionary<string, string>> Read(string _Path)
    {
        // 存储解析后的配置数据
        var _Result = new Dictionary<string, Dictionary<string, string>>();

        if (!File.Exists(_Path)) return _Result;

        // 当前正在处理的节名
        string _CurrentSection = null;

        foreach (var _RawLine in File.ReadAllLines(_Path))
        {
            string _Line = _RawLine.Trim();

            if (_Line.Length == 0 || _Line.StartsWith(';') || _Line.StartsWith('#'))
                continue;

            if (_Line.StartsWith('[') && _Line.EndsWith(']'))
            {
                _CurrentSection = _Line[1..^1];

                if (!_Result.ContainsKey(_CurrentSection))
                    _Result[_CurrentSection] = new Dictionary<string, string>();
            }
            else if (_CurrentSection != null && _Line.Contains('='))
            {
                var _Kv = _Line.Split('=', 2);
                _Result[_CurrentSection][_Kv[0].Trim()] = _Kv[1].Trim();
            }
        }

        return _Result;
    }

    /// <summary>
    /// 将配置数据写入 INI 文件
    /// </summary>
    /// <param name="_Path">保存路径</param>
    /// <param name="_Data">配置数据结构</param>
    public static void Write(string _Path, Dictionary<string, Dictionary<string, string>> _Data)
    {
        // 用于拼接 INI 内容
        var _Builder = new StringBuilder();

        foreach (var _Section in _Data)
        {
            _Builder.AppendLine($"[{_Section.Key}]");

            foreach (var _Kv in _Section.Value)
                _Builder.AppendLine($"{_Kv.Key} = {_Kv.Value}");

            _Builder.AppendLine();
        }

        File.WriteAllText(_Path, _Builder.ToString(), Encoding.UTF8);
    }
}
