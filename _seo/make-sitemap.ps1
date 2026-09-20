# Regenerates sitemap.xml from the HTML pages in the repository root.
#
# Run it from anywhere, before committing a new or changed public page:
#   powershell -ExecutionPolicy Bypass -File tools\make-sitemap.ps1
#
# Rules:
#   - only *.html in the repository root are listed (reports_html/ is noindex);
#   - pages carrying <meta name="robots" content="noindex..."> are skipped;
#   - the gated reserved area, the Search Console token file and the 404 page are skipped;
#   - <lastmod> is the date of the last git commit touching the page.
# This folder starts with an underscore, so Jekyll does not publish it.

$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
$enc = New-Object System.Text.UTF8Encoding($false)
$nl = "`r`n"
$base = 'https://tradingalgo.it'
$skip = @('google38af22d314c12ff9.html', 'reserved-area.html', '404.html')
$core = 'index.html', 'tradingalgo-mosaic.html', 'pricing.html', 'faq.html', 'framework.html', 'validation.html',
        'explore-markets.html', 'market-stocks.html', 'hedge-gauge.html', 'publications.html', 'events.html'

$pages = Get-ChildItem -Path $root -Filter *.html -File | Where-Object {
  $_.Name -notin $skip -and -not ([IO.File]::ReadAllText($_.FullName) -match 'name="robots"\s+content="[^"]*noindex')
} | ForEach-Object Name

$order = @($core | Where-Object { $_ -in $pages }) + @($pages | Where-Object { $_ -notin $core } | Sort-Object)
$sb = New-Object System.Text.StringBuilder
[void]$sb.Append('<?xml version="1.0" encoding="UTF-8"?>' + $nl + '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">' + $nl)
foreach ($f in $order) {
  $loc = if ($f -eq 'index.html') { "$base/" } else { "$base/$f" }
  $d = (git log -1 --format=%cs -- $f)
  if (-not $d) { $d = (Get-Date).ToString('yyyy-MM-dd') }   # not committed yet
  [void]$sb.Append("  <url>$nl    <loc>$loc</loc>$nl    <lastmod>$d</lastmod>$nl  </url>$nl")
}
[void]$sb.Append('</urlset>' + $nl)
[IO.File]::WriteAllText((Join-Path $root 'sitemap.xml'), $sb.ToString(), $enc)
"{0} URLs written to sitemap.xml" -f $order.Count
