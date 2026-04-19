<?php

// usage: php downgrade-kicad-to-v9.php -in path/to/schematic/or/pcb/file -out path/to/schematic/or/pcb/file/new-version

// This is in a "Works on nmy machine" state
// Use at own risk

$in = 'php://stdin';
$out = 'php://stdout';
$dryRun = false;

// Parse command-line arguments
for ($i = 1; $i < $argc; $i++) {
    if ($argv[$i] === '-in' && isset($argv[$i + 1])) {
        $in = ($argv[$i + 1] === '-') ? 'php://stdin' : $argv[$i + 1];
        $i++;
    } elseif ($argv[$i] === '-out' && isset($argv[$i + 1])) {
        $out = ($argv[$i + 1] === '-') ? 'php://stdout' : $argv[$i + 1];
        $i++;
    } elseif ($argv[$i] === '--dry-run') {
        $dryRun = true;
    }
}

// Read input
$content = file_get_contents($in);
if ($content === false) {
    fwrite(STDERR, "Error: Unable to read input file\n");
    exit(1);
}

// Store original content for diff
$originalContent = $content;

// Detect file type in first line
if (!preg_match('/^\(kicad_(sch|pcb)/', $content, $typeMatch)) {
    fwrite(STDERR, "Error: Not a valid KiCad schematic or PCB file\n");
    exit(1);
}

$fileType = $typeMatch[1]; // 'sch' or 'pcb'

// Check version
if (!preg_match('/\(version\s+(\d+)\)/', $content, $versionMatch)) {
    fwrite(STDERR, "Error: Version not found in file\n");
    exit(1);
}

$version = (int)$versionMatch[1];
if ($version < 20250114) {
    fwrite(STDERR, "Error: File version too old (not KiCad 9 or 10)\n");
    exit(1);
}

// Set version based on file type (schematic uses 20250114, pcb uses 20241229)
$targetVersion = ($fileType === 'sch') ? 20250114 : 20241229;
$content = preg_replace('/\(version\s+\d+\)/', "(version $targetVersion)", $content);

// Check if it's a KiCad 10 file
if (!preg_match('/\(generator_version\s+"10\./', $content)) {
    fwrite(STDERR, "Error: Not a KiCad 10 file\n");
    exit(1);
}

// Downgrade generator version from 10.0 to 9.0
$content = preg_replace('/\(generator_version\s+"10\.0"\)/', '(generator_version "9.0")', $content);

// Regex replacements for KiCad 9 compatibility
$content = preg_replace('/\(power\s+global\)/', '(power)', $content);
$content = preg_replace('/\n\s+\(duplicate_(pin|pad)_numbers_are_jumpers\s+(yes|no)\)/', '', $content);
$content = preg_replace('/\n\s+\(in_pos_files\s+(yes|no)\)/', '', $content);
$content = preg_replace('/\n\s+\(body_style\s+\d+\)/', '', $content);

// Tenting replacements
$content = preg_replace('/\(tenting\s+\(front\s+yes\)\s+\(back\s+yes\)\s+\)/', '(tenting front back)', $content);
$content = preg_replace('/\(tenting\s+\(front\s+no\)\s+\(back\s+no\)\s+\)/', '(tenting none)', $content);
$content = preg_replace('/\(tenting\s+\(front\s+no\)\s+\(back\s+yes\)\s+\)/', '(tenting back)', $content);
$content = preg_replace('/\(tenting\s+\(front\s+yes\)\s+\(back\s+no\)\s+\)/', '(tenting front)', $content);

// Remove capping, filling, plugging, covering sections (handle any front/back combination)
$content = preg_replace('/\n\s+\((capping|filling|plugging|covering)\s+\(front\s+(yes|no)\)\s+\(back\s+(yes|no)\)\s+\)/s', '', $content);
$content = preg_replace('/\n\s+\((capping|filling|plugging|covering)\s+(yes|no)\)/s', '', $content);

// Remove units sections
// Pattern: (units (unit (name "...") (pins ... multiline ... ) ) )
// Also handles empty pins: (pins)
$content = preg_replace('/\t+\(units\n\t+\(unit\n\t+\(name "[^)]+"\)\n\t+\(pins[^)]*(\n[^)]+)*\n?\t*\)(\n\t+\)){2}\n?/s', '', $content);

// NET replacements
$nets = [];
$netCounter = 1;
$netMap = [];

// Find all unique net names
preg_match_all('/\(net\s+"([^"]+)"\)/', $content, $netMatches);
$uniqueNets = array_unique($netMatches[1]);

// Create net list with numbers
foreach ($uniqueNets as $netName) {
    $netMap[$netName] = $netCounter;
    $nets[] = sprintf("\t(net %d \"%s\")", $netCounter, $netName);
    $netCounter++;
}

// Replace inline net mentions
foreach ($netMap as $netName => $netNum) {
    $content = str_replace(
        sprintf('(net "%s")', $netName),
        sprintf('(net %d "%s")', $netNum, $netName),
        $content
    );
}

// Insert net list before (setup ...)
if (preg_match('/(\s+\(setup\s)/', $content, $setupMatch, PREG_OFFSET_CAPTURE)) {
    $netList = "\n" . implode("\n", $nets) . "\n";
    $content = substr_replace($content, $netList, $setupMatch[0][1], 0);
}

// Function to generate unified diff
function generateUnifiedDiff($original, $modified, $fromFile, $toFile) {
    $originalLines = explode("\n", $original);
    $modifiedLines = explode("\n", $modified);

    $diff = "--- $fromFile\n";
    $diff .= "+++ $toFile\n";

    // Simple diff implementation
    $originalCount = count($originalLines);
    $modifiedCount = count($modifiedLines);
    $maxCount = max($originalCount, $modifiedCount);

    $i = 0;
    while ($i < $maxCount) {
        // Find sequences of matching lines
        $matchStart = $i;
        while ($i < $originalCount && $i < $modifiedCount &&
               $originalLines[$i] === $modifiedLines[$i]) {
            $i++;
        }

        if ($i < $maxCount) {
            // Find the end of differing section
            $diffStart = $i;

            // Look ahead to find next matching section
            $foundMatch = false;
            for ($lookahead = 1; $lookahead < 100 && !$foundMatch; $lookahead++) {
                if ($i + $lookahead < $originalCount && $i + $lookahead < $modifiedCount) {
                    if ($originalLines[$i + $lookahead] === $modifiedLines[$i + $lookahead]) {
                        $foundMatch = true;
                        break;
                    }
                }
            }

            $diffEndOrig = $foundMatch ? $i + $lookahead : $originalCount;
            $diffEndMod = $foundMatch ? $i + $lookahead : $modifiedCount;

            // Output hunk header
            $contextStart = max(0, $diffStart - 3);
            $origStart = $contextStart + 1;
            $origLen = $diffEndOrig - $contextStart;
            $modStart = $contextStart + 1;
            $modLen = $diffEndMod - $contextStart;

            $diff .= "@@ -$origStart,$origLen +$modStart,$modLen @@\n";

            // Output context before diff
            for ($j = $contextStart; $j < $diffStart; $j++) {
                if ($j < $originalCount) {
                    $diff .= " " . $originalLines[$j] . "\n";
                }
            }

            // Output removed lines
            for ($j = $diffStart; $j < $diffEndOrig; $j++) {
                if ($j < $originalCount) {
                    $diff .= "-" . $originalLines[$j] . "\n";
                }
            }

            // Output added lines
            for ($j = $diffStart; $j < $diffEndMod; $j++) {
                if ($j < $modifiedCount) {
                    $diff .= "+" . $modifiedLines[$j] . "\n";
                }
            }

            // Output context after diff (3 lines)
            for ($j = 0; $j < 3 && $diffEndOrig + $j < $originalCount; $j++) {
                $diff .= " " . $originalLines[$diffEndOrig + $j] . "\n";
            }

            $i = $foundMatch ? $i + $lookahead : $maxCount;
        }
    }

    return $diff;
}

// Write output or show diffa
if ($dryRun) {
    $inputFileName = ($in === 'php://stdin') ? 'stdin' : $in;
    $outputFileName = ($out === 'php://stdout') ? 'stdout' : $out;
    $diff = generateUnifiedDiff($originalContent, $content, $inputFileName, $outputFileName);
    fwrite(STDERR, $diff);
} else {
    if (file_put_contents($out, $content) === false) {
        fwrite(STDERR, "Error: Unable to write output file\n");
        exit(1);
    }
}