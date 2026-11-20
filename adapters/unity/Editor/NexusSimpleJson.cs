#if UNITY_EDITOR
using System;
using System.Collections;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Text;

namespace Nexus.Bridge.Editor
{
    /// <summary>
    /// Zero-dependency RFC-8259 JSON parser and serializer for Unity C# 9.0+ (no external packages required).
    /// </summary>
    internal static class NexusSimpleJson
    {
        public static object Deserialize(string json)
        {
            if (string.IsNullOrEmpty(json))
            {
                return null;
            }
            var parser = new Parser(json);
            return parser.ParseValue();
        }

        public static string Serialize(object obj)
        {
            var sb = new StringBuilder(256);
            SerializeValue(obj, sb);
            return sb.ToString();
        }

        private sealed class Parser
        {
            private readonly StringReader _reader;

            public Parser(string json)
            {
                _reader = new StringReader(json);
            }

            public object ParseValue()
            {
                EatWhitespace();
                int next = _reader.Peek();
                if (next == -1)
                {
                    return null;
                }

                char c = (char)next;
                if (c == '{') return ParseObject();
                if (c == '[') return ParseArray();
                if (c == '"') return ParseString();
                if (c == 't' || c == 'f') return ParseBool();
                if (c == 'n') return ParseNull();
                if (c == '-' || (c >= '0' && c <= '9')) return ParseNumber();

                throw new FormatException($"Unexpected JSON character '{c}'.");
            }

            private Dictionary<string, object> ParseObject()
            {
                var table = new Dictionary<string, object>(StringComparer.Ordinal);
                _reader.Read(); // '{'
                while (true)
                {
                    EatWhitespace();
                    int peek = _reader.Peek();
                    if (peek == -1) throw new FormatException("Unterminated JSON object.");
                    if ((char)peek == '}')
                    {
                        _reader.Read();
                        return table;
                    }
                    if ((char)peek == ',')
                    {
                        _reader.Read();
                        continue;
                    }
                    string key = ParseString();
                    EatWhitespace();
                    if (_reader.Read() != ':')
                    {
                        throw new FormatException("Expected ':' in JSON object.");
                    }
                    table[key] = ParseValue();
                }
            }

            private List<object> ParseArray()
            {
                var list = new List<object>();
                _reader.Read(); // '['
                while (true)
                {
                    EatWhitespace();
                    int peek = _reader.Peek();
                    if (peek == -1) throw new FormatException("Unterminated JSON array.");
                    if ((char)peek == ']')
                    {
                        _reader.Read();
                        return list;
                    }
                    if ((char)peek == ',')
                    {
                        _reader.Read();
                        continue;
                    }
                    list.Add(ParseValue());
                }
            }

            private string ParseString()
            {
                var sb = new StringBuilder();
                if (_reader.Read() != '"')
                {
                    throw new FormatException("Expected '\"' at start of JSON string.");
                }
                while (true)
                {
                    int ch = _reader.Read();
                    if (ch == -1) throw new FormatException("Unterminated JSON string.");
                    char c = (char)ch;
                    if (c == '"') break;
                    if (c == '\\')
                    {
                        int esc = _reader.Read();
                        if (esc == -1) throw new FormatException("Unterminated escape in JSON string.");
                        switch ((char)esc)
                        {
                            case '"': sb.Append('"'); break;
                            case '\\': sb.Append('\\'); break;
                            case '/': sb.Append('/'); break;
                            case 'b': sb.Append('\b'); break;
                            case 'f': sb.Append('\f'); break;
                            case 'n': sb.Append('\n'); break;
                            case 'r': sb.Append('\r'); break;
                            case 't': sb.Append('\t'); break;
                            case 'u':
                                var hex = new char[4];
                                for (int i = 0; i < 4; i++)
                                {
                                    int h = _reader.Read();
                                    if (h == -1) throw new FormatException("Invalid unicode escape.");
                                    hex[i] = (char)h;
                                }
                                sb.Append((char)Convert.ToInt32(new string(hex), 16));
                                break;
                            default:
                                sb.Append((char)esc);
                                break;
                        }
                    }
                    else
                    {
                        sb.Append(c);
                    }
                }
                return sb.ToString();
            }

            private object ParseNumber()
            {
                var sb = new StringBuilder();
                bool isFloat = false;
                while (true)
                {
                    int peek = _reader.Peek();
                    if (peek == -1) break;
                    char c = (char)peek;
                    if ("0123456789+-eE.".IndexOf(c) == -1) break;
                    if (c == '.' || c == 'e' || c == 'E') isFloat = true;
                    sb.Append((char)_reader.Read());
                }
                string raw = sb.ToString();
                if (isFloat)
                {
                    return double.Parse(raw, CultureInfo.InvariantCulture);
                }
                if (long.TryParse(raw, NumberStyles.Integer, CultureInfo.InvariantCulture, out long lVal))
                {
                    return lVal;
                }
                return double.Parse(raw, CultureInfo.InvariantCulture);
            }

            private bool ParseBool()
            {
                string word = ReadWord();
                if (word == "true") return true;
                if (word == "false") return false;
                throw new FormatException($"Unexpected literal '{word}'.");
            }

            private object ParseNull()
            {
                string word = ReadWord();
                if (word == "null") return null;
                throw new FormatException($"Unexpected literal '{word}'.");
            }

            private string ReadWord()
            {
                var sb = new StringBuilder();
                while (true)
                {
                    int peek = _reader.Peek();
                    if (peek == -1) break;
                    char c = (char)peek;
                    if (!char.IsLetter(c)) break;
                    sb.Append((char)_reader.Read());
                }
                return sb.ToString();
            }

            private void EatWhitespace()
            {
                while (_reader.Peek() != -1 && char.IsWhiteSpace((char)_reader.Peek()))
                {
                    _reader.Read();
                }
            }
        }

        private static void SerializeValue(object value, StringBuilder sb)
        {
            if (value == null)
            {
                sb.Append("null");
                return;
            }
            if (value is string s)
            {
                SerializeString(s, sb);
                return;
            }
            if (value is bool b)
            {
                sb.Append(b ? "true" : "false");
                return;
            }
            if (value is IDictionary dict)
            {
                sb.Append('{');
                bool first = true;
                foreach (DictionaryEntry entry in dict)
                {
                    if (!first) sb.Append(',');
                    SerializeString(Convert.ToString(entry.Key, CultureInfo.InvariantCulture) ?? string.Empty, sb);
                    sb.Append(':');
                    SerializeValue(entry.Value, sb);
                    first = false;
                }
                sb.Append('}');
                return;
            }
            if (value is IEnumerable list && !(value is string))
            {
                sb.Append('[');
                bool first = true;
                foreach (object item in list)
                {
                    if (!first) sb.Append(',');
                    SerializeValue(item, sb);
                    first = false;
                }
                sb.Append(']');
                return;
            }
            if (value is float f)
            {
                sb.Append(float.IsNaN(f) || float.IsInfinity(f) ? "0" : f.ToString("R", CultureInfo.InvariantCulture));
                return;
            }
            if (value is double d)
            {
                sb.Append(double.IsNaN(d) || double.IsInfinity(d) ? "0" : d.ToString("R", CultureInfo.InvariantCulture));
                return;
            }
            if (value is int || value is long || value is short || value is byte || value is uint || value is ulong)
            {
                sb.Append(Convert.ToString(value, CultureInfo.InvariantCulture));
                return;
            }
            SerializeString(Convert.ToString(value, CultureInfo.InvariantCulture) ?? string.Empty, sb);
        }

        private static void SerializeString(string str, StringBuilder sb)
        {
            sb.Append('"');
            foreach (char c in str)
            {
                switch (c)
                {
                    case '"': sb.Append("\\\""); break;
                    case '\\': sb.Append("\\\\"); break;
                    case '\b': sb.Append("\\b"); break;
                    case '\f': sb.Append("\\f"); break;
                    case '\n': sb.Append("\\n"); break;
                    case '\r': sb.Append("\\r"); break;
                    case '\t': sb.Append("\\t"); break;
                    default:
                        if (c < ' ' || c > 126)
                        {
                            sb.Append("\\u");
                            sb.Append(((int)c).ToString("x4", CultureInfo.InvariantCulture));
                        }
                        else
                        {
                            sb.Append(c);
                        }
                        break;
                }
            }
            sb.Append('"');
        }
    }
}
#endif
