using System;
using System.Collections.Generic;
using System.Globalization;
using System.Linq;
using System.Text.Json;

namespace Aive.UI2.Announcements;

public static class AnnouncementParser
{
	public static IReadOnlyList<Announcement> Parse(ReadOnlyMemory<byte> json, string productId, Action<string> log)
	{
		using JsonDocument document = JsonDocument.Parse(json, new JsonDocumentOptions
		{
			MaxDepth = 24
		});
		JsonElement root = document.RootElement;
		if (root.ValueKind == JsonValueKind.Object)
		{
			JsonElement? jsonElement = Field(root, "success");
			if (jsonElement.HasValue && jsonElement.GetValueOrDefault().ValueKind == JsonValueKind.False)
			{
				throw new JsonException("API returned failure");
			}
			root = Field(root, "items") ?? Field(root, "announcements") ?? Field(root, "data") ?? root;
			if (root.ValueKind == JsonValueKind.Object)
			{
				root = Field(root, "items") ?? Field(root, "announcements") ?? root;
			}
		}
		if (root.ValueKind != JsonValueKind.Array || root.GetArrayLength() > 200)
		{
			throw new JsonException("Expected an announcement array (maximum 200 items)");
		}
		List<Announcement> result = new List<Announcement>();
		HashSet<string> seen = new HashSet<string>(StringComparer.Ordinal);
		int structurallyValid = 0;
		foreach (JsonElement row in root.EnumerateArray())
		{
			try
			{
				if (row.ValueKind != JsonValueKind.Object)
				{
					throw new JsonException("Invalid announcement object");
				}
				JsonElement? id = Field(row, "id");
				string key = id?.ValueKind switch
				{
					JsonValueKind.String => id.Value.GetString() ?? "",
					JsonValueKind.Number => id.Value.GetRawText(),
					_ => "",
				};
				string content = Text(row, "content", 8000);
				int length = key.Length;
				bool flag = ((length > 128 || length == 0) ? true : false);
				if (flag || string.IsNullOrWhiteSpace(content))
				{
					throw new JsonException("Missing id/content");
				}
				DateTimeOffset? start = Date(row, "startTime");
				DateTimeOffset? end = Date(row, "endTime");
				if (start.HasValue && end.HasValue && end <= start)
				{
					throw new JsonException("Invalid validity interval");
				}
				string title = Text(row, "title", 200);
				string type = Text(row, "type", 30);
				string linkText = Text(row, "linkText", 120);
				string link = Text(row, "linkUrl", 2048);
				DateTimeOffset? updated = Date(row, "updatedAt");
				JsonElement? jsonElement = Field(row, "priority");
				int num;
				if (jsonElement.HasValue)
				{
					JsonElement p = jsonElement.GetValueOrDefault();
					if (p.ValueKind == JsonValueKind.Number && p.TryGetInt32(out var n))
					{
						num = n;
						goto IL_0336;
					}
				}
				num = 0;
				goto IL_0336;
				IL_0336:
				int priority = num;
				structurallyValid++;
				if (!TargetMatches(row, productId))
				{
					continue;
				}
				string status = Text(row, "status", 30);
				flag = status.Length > 0;
				if (flag)
				{
					bool flag2 = ((status == "published" || status == "active") ? true : false);
					flag = !flag2;
				}
				if (flag)
				{
					continue;
				}
				jsonElement = Field(row, "enabled");
				if (jsonElement.HasValue && jsonElement.GetValueOrDefault().ValueKind == JsonValueKind.False)
				{
					continue;
				}
				jsonElement = Field(row, "isActive");
				if (!jsonElement.HasValue || jsonElement.GetValueOrDefault().ValueKind != JsonValueKind.False)
				{
					if (link.Length > 0 && !AnnouncementUrlPolicy.TryGetWebUri(link, out Uri _))
					{
						log("Warning: announcement URL blocked for id=" + key);
						link = "";
					}
					if (seen.Add(key))
					{
						result.Add(new Announcement(key, title, content, type, priority, linkText, link, start, end, updated));
					}
				}
			}
			catch (JsonException ex)
			{
				log("Warning: invalid announcement skipped: " + ex.Message);
			}
		}
		if (root.GetArrayLength() > 0 && structurallyValid == 0)
		{
			throw new JsonException("No structurally valid announcements");
		}
		return result;
	}

	private static bool TargetMatches(JsonElement row, string productId)
	{
		JsonElement? jsonElement = Field(row, "isGlobal");
		if (jsonElement.HasValue && jsonElement.GetValueOrDefault().ValueKind == JsonValueKind.True)
		{
			return true;
		}
		jsonElement = Field(row, "productIds");
		if (jsonElement.HasValue)
		{
			JsonElement ids = jsonElement.GetValueOrDefault();
			if (ids.ValueKind != JsonValueKind.Array)
			{
				throw new JsonException("Invalid productIds");
			}
			return ids.EnumerateArray().Any((JsonElement x) => x.ValueKind == JsonValueKind.String && string.Equals(x.GetString(), productId, StringComparison.OrdinalIgnoreCase));
		}
		jsonElement = Field(row, "productId");
		if (jsonElement.HasValue)
		{
			JsonElement id = jsonElement.GetValueOrDefault();
			if (id.ValueKind != JsonValueKind.Null)
			{
				if (id.ValueKind == JsonValueKind.String)
				{
					return string.Equals(id.GetString(), productId, StringComparison.OrdinalIgnoreCase);
				}
				return false;
			}
		}
		jsonElement = Field(row, "isGlobal");
		return !jsonElement.HasValue || jsonElement.GetValueOrDefault().ValueKind != JsonValueKind.False;
	}

	private static string Text(JsonElement row, string name, int max)
	{
		JsonElement? value = Field(row, name);
		if (!value.HasValue || value.Value.ValueKind == JsonValueKind.Null)
		{
			return "";
		}
		if (value.Value.ValueKind != JsonValueKind.String)
		{
			throw new JsonException("Invalid " + name);
		}
		string? obj = value.Value.GetString() ?? "";
		if (obj.Length > max)
		{
			throw new JsonException(name + " too long");
		}
		return obj;
	}

	private static DateTimeOffset? Date(JsonElement row, string name)
	{
		string text = Text(row, name, 64);
		if (text.Length == 0)
		{
			return null;
		}
		if (!DateTimeOffset.TryParse(text, CultureInfo.InvariantCulture, DateTimeStyles.AdjustToUniversal | DateTimeStyles.AssumeUniversal, out var value))
		{
			throw new JsonException("Invalid " + name);
		}
		return value;
	}

	private static JsonElement? Field(JsonElement row, string name)
	{
		foreach (JsonProperty property in row.EnumerateObject())
		{
			if (string.Equals(property.Name.Replace("_", ""), name, StringComparison.OrdinalIgnoreCase))
			{
				return property.Value;
			}
		}
		return null;
	}
}
