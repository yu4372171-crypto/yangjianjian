using System;

namespace Aive.UI2.Announcements;

public sealed record Announcement(string Id, string Title, string Content, string Type, int Priority, string LinkText, string LinkUrl, DateTimeOffset? StartTime, DateTimeOffset? EndTime, DateTimeOffset? UpdatedAt)
{
	public bool IsValidAt(DateTimeOffset now)
	{
		if (!StartTime.HasValue || StartTime <= now)
		{
			if (EndTime.HasValue)
			{
				return EndTime > now;
			}
			return true;
		}
		return false;
	}
}
