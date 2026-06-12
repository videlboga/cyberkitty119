<?php
/**
 * WIKI-BOILERPLATE-D: Fix 5 regressions + 4 RU Bambu AI articles
 *
 * 1. Type A regressions: "we recommend submitting a regarding your issue" (3 articles)
 *    - Replace with proper Russian or remove entirely
 * 2. Type B regressions: "please and </p>" (2 articles)
 *    - Remove dangling "and", replace block with cleaned version
 * 3. RU Bambu AI blocks in Russian text (4 articles)
 *    - Remove entire block with Bambu AI links to support.bambulab.cn/cn
 */
define('IBLOCK_ID', 60);
$db = new mysqli('localhost', 'bitrix0', 'lwtSNYi-8p?aCHkQR6-H', 'sitemanager');
if ($db->connect_error) die("DB connect failed\n");
$db->set_charset('utf8');
echo "=== WIKI-BOILERPLATE-D: Regression fix ===\n\n";

$stmt = $db->prepare("UPDATE b_iblock_element SET DETAIL_TEXT = ?, TIMESTAMP_X = NOW() WHERE ID = ?");

$updated = 0;
$skipped = 0;

// ==================================================================
// PART 1: Fix Type A regressions — "we recommend submitting a regarding your issue"
// ==================================================================
echo "--- Part 1: Type A (submitting a regarding) ---\n";
$r = $db->query("SELECT ID, CODE, DETAIL_TEXT FROM b_iblock_element 
    WHERE IBLOCK_ID=60 AND DETAIL_TEXT LIKE '%we recommend submitting a regarding%'
    ORDER BY ID");
while ($row = $r->fetch_assoc()) {
    $id = (int)$row['ID'];
    $text = $row['DETAIL_TEXT'];
    $orig = $text;

    // These are <blockquote><p> End Notes blocks. Clean up the entire blockquote.
    // Pattern: "we recommend submitting a regarding your issue"
    // Replace with properly formatted Russian or remove
    $text = preg_replace(
        '~<blockquote>\s*<p>\s*To ensure a safe and effective execution, if you have any concerns or questions about the process described in this article, we recommend submitting a regarding your issue\.\s*Please include a picture or video illustrating the problem, as well as any additional information related to your inquiry\.\s*</p>\s*</blockquote>~is',
        '',
        $text
    );

    // Also try variations
    $text = preg_replace(
        '~<blockquote>\s*<p>\s*[^<]*?we recommend submitting a regarding your issue[^<]*?</p>\s*</blockquote>~is',
        '',
        $text
    );

    if ($text === $orig) {
        echo "  ID $id: no match, skipping\n";
        $skipped++;
        continue;
    }
    $stmt->bind_param('si', $text, $id);
    if ($stmt->execute()) {
        echo "  ID $id: fixed ✅\n";
        $updated++;
    }
}

// ==================================================================
// PART 2: Fix Type B regressions — "please and </p>"
// ==================================================================
echo "\n--- Part 2: Type B (please and </p>) ---\n";
$r = $db->query("SELECT ID, CODE, DETAIL_TEXT FROM b_iblock_element 
    WHERE IBLOCK_ID=60 AND DETAIL_TEXT LIKE '%please and%' AND DETAIL_TEXT LIKE '%concerns%'
    ORDER BY ID");
while ($row = $r->fetch_assoc()) {
    $id = (int)$row['ID'];
    $text = $row['DETAIL_TEXT'];
    $orig = $text;

    // Remove the entire <p> that contains "please and "
    $text = preg_replace(
        '~<p>\s*For any concerns or questions about following this guide, please and\s*</p>~is',
        '',
        $text
    );

    // Also try with <blockquote> wrapper
    $text = preg_replace(
        '~<blockquote>\s*<p>\s*[^<]*?please and\s*</p>\s*</blockquote>~is',
        '',
        $text
    );

    // Also try any <p> with "please and" dangling
    $text = preg_replace(
        '~<p>[^<]*?please\s+and\s*</p>~is',
        '',
        $text
    );

    if ($text === $orig) {
        echo "  ID $id: no match, skipping\n";
        $skipped++;
        continue;
    }
    $stmt->bind_param('si', $text, $id);
    if ($stmt->execute()) {
        echo "  ID $id: fixed ✅\n";
        $updated++;
    }
}

// ==================================================================
// PART 3: Remove RU-translated Bambu AI blocks
// ==================================================================
echo "\n--- Part 3: RU-translated Bambu AI blocks ---\n";
$r = $db->query("SELECT ID, CODE, DETAIL_TEXT FROM b_iblock_element 
    WHERE IBLOCK_ID=60 AND DETAIL_TEXT LIKE '%Bambu AI%' AND DETAIL_TEXT LIKE '%support.bambulab.cn%'
    ORDER BY ID");
while ($row = $r->fetch_assoc()) {
    $id = (int)$row['ID'];
    $text = $row['DETAIL_TEXT'];
    $orig = $text;

    // Pattern 1: "Нажмите здесь, чтобы получить доступ к Bambu AI [link] и здесь, чтобы отправить запрос"
    $text = preg_replace(
        '~Нажмите здесь, чтобы получить доступ к Bambu AI\s*\[?\s*<a\s+href="https?://support\.bambulab\.cn/[^"]*"[^>]*>https?://support\.bambulab\.cn/[^<]*</a>\s*\]?\s*и здесь, чтобы отправить\s+запрос\s+(?:в службу поддержки\s+)?\[?\s*<a\s+href="[^"]*"[^>]*>[^<]*</a>\s*\]?\s*~is',
        '',
        $text
    );

    // Pattern 2: "Нажмите здесь, чтобы перейти в Bambu AI [link] нажмите здесь, чтобы отправить запрос в службу поддержки обратитесь в службу поддержки Bambu Lab"
    $text = preg_replace(
        '~Нажмите здесь, чтобы перейти в Bambu AI\s*\[?\s*<a\s+href="https?://support\.bambulab\.cn/[^"]*"[^>]*>https?://support\.bambulab\.cn/[^<]*</a>\s*\]?\s*нажмите здесь, чтобы отправить запрос в службу поддержки\s*обратитесь в службу поддержки Bambu Lab\s*~is',
        '',
        $text
    );

    // Pattern 3: "Нажмите здесь, чтобы получить доступ к Bambu AI [link] и здесь, чтобы подать заявку в службу поддержки [link]"
    $text = preg_replace(
        '~Нажмите здесь, чтобы получить доступ к Bambu AI\s*\[?\s*<a\s+href="https?://support\.bambulab\.cn/[^"]*"[^>]*>https?://support\.bambulab\.cn/[^<]*</a>\s*\]?\s*и здесь, чтобы подать заявку в службу поддержки\s*\[?\s*<a\s+href="[^"]*"[^>]*>[^<]*</a>\s*\]?\s*~is',
        '',
        $text
    );

    // Pattern 4: "Нажмите здесь, чтобы получить доступ к Bambu AI [link] и нажмите здесь, чтобы создать запрос в службу поддержки обратитесь в службу поддержки Bambu Lab"
    $text = preg_replace(
        '~Нажмите здесь, чтобы получить доступ к Bambu AI\s*\[?\s*<a\s+href="https?://support\.bambulab\.cn/[^"]*"[^>]*>https?://support\.bambulab\.cn/[^<]*</a>\s*\]?\s*и нажмите здесь, чтобы создать запрос в службу поддержки\s*обратитесь в службу поддержки Bambu Lab\s*~is',
        '',
        $text
    );

    // Catch-all: any Russian text containing "Bambu AI" with support.bambulab.cn link
    $text = preg_replace(
        '~[^.]*?Нажмите здесь[^.]*?Bambu AI[^.]*?support\.bambulab\.cn[^.]*?\.?\s*~isu',
        '',
        $text
    );

    if ($text === $orig) {
        echo "  ID $id: no match, skipping\n";
        $skipped++;
        continue;
    }
    $stmt->bind_param('si', $text, $id);
    if ($stmt->execute()) {
        echo "  ID $id: fixed ✅\n";
        $updated++;
    }
}

// ==================================================================
// Cleanup pass: fix any remaining broken/empty HTML
// ==================================================================
echo "\n--- Cleanup: empty HTML artifacts ---\n";
$cleanup_ids = [12502, 12507, 12639, 12155, 12177, 10075, 10265, 10580, 11040];
foreach ($cleanup_ids as $id) {
    $r = $db->query("SELECT ID, DETAIL_TEXT FROM b_iblock_element WHERE IBLOCK_ID=60 AND ID=$id");
    $row = $r->fetch_assoc();
    if (!$row) continue;
    $text = $row['DETAIL_TEXT'];
    $orig = $text;

    // Empty <a> tags
    $text = preg_replace('~<a[^>]*>\s*</a>~i', '', $text);
    // Empty <strong>/<em>/<i>
    $text = preg_replace('~<(strong|em|i|b)>\s*</\1>~i', '', $text);
    // Empty <p>
    $text = preg_replace('~<p>\s*(?:<br\s*/?>)?\s*</p>~i', '', $text);
    // Empty <blockquote>
    $text = preg_replace('~<blockquote>\s*(?:<br\s*/?>\s*)?(?:<p>\s*</p>\s*)?</blockquote>~i', '', $text);
    // Consecutive whitespace
    $text = preg_replace('/ {2,}/', ' ', $text);
    $text = preg_replace("/\n{3,}/", "\n\n", $text);
    $text = trim($text);

    if ($text !== $orig && strlen($text) > 0) {
        $stmt->bind_param('si', $text, $id);
        if ($stmt->execute()) {
            echo "  ID $id: cleanup applied\n";
            $updated++;
        }
    }
}

echo "\n=== RESULT ===\n";
echo "Updated: $updated\nSkipped: $skipped\n";

// Verification
echo "\n=== VERIFICATION ===\n";
$tests = [
    "submitting a regarding" => "we recommend submitting a regarding",
    "please and" => "DETAIL_TEXT LIKE '%please and%' AND DETAIL_TEXT LIKE '%concerns%'",
];
$fail = 0;
foreach ($tests as $name => $like) {
    $r2 = $db->query("SELECT COUNT(*) as c FROM b_iblock_element WHERE IBLOCK_ID=60 AND DETAIL_TEXT LIKE '%$like%'");
    $c = (int)$r2->fetch_assoc()['c'];
    if ($c > 0) { echo "  '$name': $c remaining ❌\n"; $fail += $c; }
    else { echo "  '$name': 0 ✅\n"; }
}

// Bambu AI + cn check
$r2 = $db->query("SELECT COUNT(*) as c FROM b_iblock_element WHERE IBLOCK_ID=60 AND DETAIL_TEXT LIKE '%Bambu AI%' AND DETAIL_TEXT LIKE '%support.bambulab.cn%'");
$c = (int)$r2->fetch_assoc()['c'];
if ($c > 0) { echo "  'Bambu AI + cn': $c remaining ❌\n"; $fail += $c; }
else { echo "  'Bambu AI + cn': 0 ✅\n"; }

if ($fail === 0) echo "\nSUCCESS! All fixes applied. 🎉\n";
else echo "\nWARNING: $fail remaining items need review.\n";