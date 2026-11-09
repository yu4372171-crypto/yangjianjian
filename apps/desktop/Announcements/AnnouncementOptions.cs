using System;

namespace Aive.UI2.Announcements;

public sealed record AnnouncementOptions(string ProductId, string Version, Uri Endpoint, string CacheDirectory, TimeSpan RefreshInterval)
{
	public Uri RequestUri => new Uri(Endpoint.AbsoluteUri + (string.IsNullOrEmpty(Endpoint.Query) ? "?" : "&") + "product_id=" + Uri.EscapeDataString(ProductId) + "&version=" + Uri.EscapeDataString(Version));
}
