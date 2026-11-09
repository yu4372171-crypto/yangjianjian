using System;
using System.Linq;

namespace Aive.UI2.Announcements;

public static class AnnouncementUrlPolicy
{
	public static bool TryGetWebUri(string? value, out Uri uri)
	{
		uri = null;
		if (string.IsNullOrWhiteSpace(value) || value.Length > 2048 || value.Any(char.IsControl) || value.Contains('\\'))
		{
			return false;
		}
		Uri candidate;
		bool flag = !Uri.TryCreate(value, UriKind.Absolute, out candidate);
		if (!flag)
		{
			string scheme = candidate.Scheme;
			bool flag2 = ((scheme == "https" || scheme == "http") ? true : false);
			flag = !flag2;
		}
		if (flag || string.IsNullOrWhiteSpace(candidate.Host) || candidate.UserInfo.Length != 0)
		{
			return false;
		}
		uri = candidate;
		return true;
	}
}
