// ─────────────────────────────────────────────────────────────────────────────
// 项目：VoiceSystem
// 文件：WavUtility.cs
// 作者：Maddie
// 日期：2025年04月23日
// ─────────────────────────────────────────────────────────────────────────────
// 说明：提供音频数据与 WAV 格式的互转方法，包括从 AudioClip 生成 WAV 和解码 Base64 PCM 数据。
// ─────────────────────────────────────────────────────────────────────────────

// VoiceSystem/Runtime/WavUtility.cs
using System;
using System.IO;
using System.Text;
using UnityEngine;

public static class WavUtility
{
    /// <summary>
    /// 将 Unity 引擎中的 AudioClip 对象转换为标准 WAV 格式的 PCM 字节数组（16-bit 深度）。
    /// 常用于将游戏录音数据导出为可跨平台播放或上传的音频文件。
    /// </summary>
    /// <param name="_Clip">需要转换的音频片段，必须为非 null 的 AudioClip 实例</param>
    /// <returns>包含 WAV 文件格式头和 PCM 音频数据的字节数组，可直接写入文件</returns>
    public static byte[] FromAudioClip(AudioClip _Clip)
    {
        if (_Clip == null)
            throw new ArgumentNullException(nameof(_Clip));

        // 获取音频的原始采样数据（浮点数数组）
        float[] _Samples = new float[_Clip.samples * _Clip.channels];
        _Clip.GetData(_Samples, 0);

        // 创建短整型数组存储 16bit PCM 数据
        short[] _IntData = new short[_Samples.Length];

        // 创建字节数组，每个采样点占 2 字节（16bit）
        byte[] _BytesData = new byte[_Samples.Length * 2];

        // 缩放因子，将浮点数范围 [-1.0, 1.0] 转换为 [-32768, 32767]
        int _RescaleFactor = short.MaxValue;

        for (int i = 0; i < _Samples.Length; i++)
        {
            // 将浮点样本转换为 16-bit 整数
            _IntData[i] = (short)(_Samples[i] * _RescaleFactor);

            // 将 16-bit 整数转换为字节（小端序）并写入数组
            byte[] _ByteArr = BitConverter.GetBytes(_IntData[i]);
            _ByteArr.CopyTo(_BytesData, i * 2);
        }

        // 创建内存流以写入 WAV 文件内容
        using MemoryStream _Stream = new MemoryStream();
        using BinaryWriter _Writer = new BinaryWriter(_Stream);

        int _HeaderSize = 44;
        int _FileSize = _HeaderSize + _BytesData.Length;

        // 写入 WAV 文件头（RIFF）
        _Writer.Write(Encoding.UTF8.GetBytes("RIFF"));            // 标识头 "RIFF"
        _Writer.Write(_FileSize - 8);                             // 文件大小减去 "RIFF" 和大小字段（共 8 字节）
        _Writer.Write(Encoding.UTF8.GetBytes("WAVE"));            // 文件类型 "WAVE"

        // 写入 fmt 子块
        _Writer.Write(Encoding.UTF8.GetBytes("fmt "));
        _Writer.Write(16);                                        // 子块大小（16表示PCM）
        _Writer.Write((ushort)1);                                 // 音频格式 1 = PCM
        _Writer.Write((ushort)_Clip.channels);                    // 声道数
        _Writer.Write(_Clip.frequency);                           // 采样率（Hz）
        _Writer.Write(_Clip.frequency * _Clip.channels * 2);      // 字节率 = 采样率 × 声道 × 位深/8
        _Writer.Write((ushort)(_Clip.channels * 2));              // 区块对齐 = 声道 × 位深/8
        _Writer.Write((ushort)16);                                // 每个样本 16bit

        // 写入 data 子块
        _Writer.Write(Encoding.UTF8.GetBytes("data"));            // 子块标识
        _Writer.Write(_BytesData.Length);                         // PCM 数据长度（字节数）
        _Writer.Write(_BytesData);                                // 实际音频数据

        // 返回 WAV 文件的字节数组
        _Writer.Flush();
        return _Stream.ToArray();
    }


    /// <summary>
    /// 给一段裸 PCM 音频数据添加 WAV 文件格式头，生成标准的 WAV 文件内容。
    /// 常用于网络音频流处理或非 Unity 平台保存兼容格式。
    /// </summary>
    /// <param name="_RawPcmData">原始 PCM 数据，必须是 8 位或 16 位单声道或立体声音频</param>
    /// <param name="_Channels">音频声道数，1 = 单声道，2 = 立体声</param>
    /// <param name="_SampleRate">采样率（单位：Hz），如 16000 表示每秒 16000 个采样</param>
    /// <param name="_BitsPerSample">每个采样点的位深，常见值为 8 或 16</param>
    /// <returns>添加 WAV 文件头后的完整音频字节数据</returns>
    public static byte[] AddWavHeader(byte[] _RawPcmData, int _Channels, int _SampleRate, int _BitsPerSample)
    {
        MemoryStream _Stream = new MemoryStream();
        BinaryWriter _Writer = new BinaryWriter(_Stream);

        // 计算参数
        int _ByteRate = _SampleRate * _Channels * _BitsPerSample / 8;
        int _BlockAlign = _Channels * _BitsPerSample / 8;
        int _DataLength = _RawPcmData.Length;
        int _FileSize = 44 + _DataLength - 8;

        // 写入 RIFF 文件头
        _Writer.Write(Encoding.ASCII.GetBytes("RIFF"));
        _Writer.Write(_FileSize);                         // 文件总长度 - 8 字节（RIFF 标识 + 4字节长度）
        _Writer.Write(Encoding.ASCII.GetBytes("WAVE"));   // 标识类型：WAVE

        // 写入 fmt 块
        _Writer.Write(Encoding.ASCII.GetBytes("fmt "));
        _Writer.Write(16);                                // PCM 固定为 16
        _Writer.Write((ushort)1);                         // 格式码 1 = PCM
        _Writer.Write((ushort)_Channels);                 // 声道数
        _Writer.Write(_SampleRate);                       // 采样率
        _Writer.Write(_ByteRate);                         // 每秒数据字节数
        _Writer.Write((ushort)_BlockAlign);               // 数据块对齐大小
        _Writer.Write((ushort)_BitsPerSample);            // 每个样本的位数

        // 写入 data 块
        _Writer.Write(Encoding.ASCII.GetBytes("data"));
        _Writer.Write(_DataLength);                       // PCM 数据长度
        _Writer.Write(_RawPcmData);                       // PCM 数据主体

        return _Stream.ToArray();                         // 返回合成后的完整 WAV 文件
    }


    /// <summary>
    /// 从标准 WAV 格式的字节数据中解析出 Unity 可播放的 AudioClip 实例。
    /// 支持 8 位或 16 位 PCM 编码，支持单声道与立体声音频。
    /// 可用于将外部音频导入游戏进行播放或处理。
    /// </summary>
    /// <param name="_WavData">WAV 字节数组，包含文件头和音频数据</param>
    /// <param name="_Offset">起始偏移位置，通常为 0</param>
    /// <param name="_ClipName">创建的 AudioClip 在 Unity 中的标识名称</param>
    /// <returns>解析成功的 AudioClip 对象；失败时返回 null</returns>
    public static AudioClip ToAudioClip(byte[] _WavData, int _Offset, string _ClipName)
    {
        if (_WavData == null || _WavData.Length < 44)
        {
            Debug.LogError("WavUtility.ToAudioClip: WAV 数据太短或为空！");
            return null;
        }

        // 检查文件头是否为合法的 RIFF/WAVE
        if (Encoding.ASCII.GetString(_WavData, _Offset, 4) != "RIFF" ||
            Encoding.ASCII.GetString(_WavData, _Offset + 8, 4) != "WAVE")
        {
            Debug.LogError("WavUtility.ToAudioClip: 非法 WAV 文件头！");
            return null;
        }

        // 查找 fmt 和 data 子块
        int _Pointer = _Offset + 12;
        int _FmtOffset = -1, _DataOffset = -1;

        while (_Pointer + 8 < _WavData.Length)
        {
            string _ChunkID = Encoding.ASCII.GetString(_WavData, _Pointer, 4);
            int _ChunkSize = BitConverter.ToInt32(_WavData, _Pointer + 4);

            if (_ChunkID == "fmt ")
                _FmtOffset = _Pointer;
            else if (_ChunkID == "data")
            {
                _DataOffset = _Pointer;
                break;
            }

            _Pointer += 8 + _ChunkSize;
        }

        if (_FmtOffset == -1 || _DataOffset == -1)
        {
            Debug.LogError("WavUtility.ToAudioClip: 找不到 fmt 或 data 块！");
            return null;
        }

        // 提取格式信息
        ushort _Format = BitConverter.ToUInt16(_WavData, _FmtOffset + 8);
        ushort _Channels = BitConverter.ToUInt16(_WavData, _FmtOffset + 10);
        int _SampleRate = BitConverter.ToInt32(_WavData, _FmtOffset + 12);
        ushort _BitsPerSample = BitConverter.ToUInt16(_WavData, _FmtOffset + 22);

        if (_Format != 1 || (_BitsPerSample != 8 && _BitsPerSample != 16))
        {
            Debug.LogError("WavUtility.ToAudioClip: 仅支持 PCM 格式 8/16bit");
            return null;
        }

        // 读取 data 数据块内容
        int _DataSize = BitConverter.ToInt32(_WavData, _DataOffset + 4);
        int _DataIndex = _DataOffset + 8;

        if (_DataIndex + _DataSize > _WavData.Length)
        {
            Debug.LogWarning("WavUtility.ToAudioClip: 数据块超出文件范围，可能损坏");
            _DataSize = _WavData.Length - _DataIndex;
        }

        int _BytesPerSample = _BitsPerSample / 8;
        int _TotalSamples = _DataSize / _BytesPerSample;

        if (_Channels == 2)
            _TotalSamples /= 2;

        float[] _FloatSamples = new float[_TotalSamples * _Channels];

        if (_BitsPerSample == 16)
        {
            for (int i = 0, j = 0; i < _DataSize; i += 2)
                _FloatSamples[j++] = BitConverter.ToInt16(_WavData, _DataIndex + i) / 32768f;
        }
        else
        {
            for (int i = 0; i < _DataSize; i++)
                _FloatSamples[i] = (_WavData[_DataIndex + i] - 128) / 128f;
        }

        // 创建并返回 AudioClip
        AudioClip _Clip = AudioClip.Create(_ClipName, _TotalSamples, _Channels, _SampleRate, false);
        _Clip.SetData(_FloatSamples, 0);
        return _Clip;
    }

}
