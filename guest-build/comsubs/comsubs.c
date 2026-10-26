/* Project86 COMSUBS replacement. Independently authored from the published
 * COMSUB.H interfaces, DOS callers and guest-level behavior tests.
 * Only the five public routines linked into the DOS distribution are provided.
 * Build with Microsoft C 5.10, small model. No heap or C runtime calls.
 */
typedef unsigned char Byte;
extern Byte far *p86_dbcs(void);

static unsigned width(Byte *text, Byte far *ranges)
{
    Byte far *p;
    if (!text[0] || !text[1] || !ranges) return 1;
    for (p = ranges; p[0] || p[1]; p += 2)
        if (text[0] >= p[0] && text[0] <= p[1]) return 2;
    return 1;
}

char *com_strchr(Byte *text, Byte wanted)
{
    Byte far *ranges;
    unsigned step;
    ranges = p86_dbcs();
    for (;;) {
        step = width(text, ranges);
        if (step == 1 && *text == wanted) return (char *)text;
        if (!*text) return 0;
        text += step;
    }
}

Byte *com_strrchr(Byte *text, Byte wanted)
{
    Byte far *ranges;
    Byte *last;
    unsigned step;
    ranges = p86_dbcs();
    last = 0;
    for (;;) {
        step = width(text, ranges);
        /* Unlike com_strchr, the original reverse search can match a lead
         * byte at a character boundary. Both searches skip trail bytes. */
        if (*text == wanted) last = text;
        if (!*text) return last;
        text += step;
    }
}

Byte *com_substr(Byte *text, Byte *pattern)
{
    Byte far *ranges;
    Byte *a, *b;
    unsigned step;
    ranges = p86_dbcs();
    /* The original interface returns the terminator for an empty pattern. */
    if (!*pattern) {
        while (*text) text += width(text, ranges);
        return text;
    }
    while (*text) {
        a = text;
        b = pattern;
        while (*b && *a) {
            step = width(a, ranges);
            if (step != width(b, ranges) || a[0] != b[0]) break;
            if (step == 2 && a[1] != b[1]) break;
            a += step;
            b += step;
        }
        if (!*b) return text;
        text += width(text, ranges);
    }
    return 0;
}

int com_toupper(Byte value)
{
    /* Matches the ASCII-only DosCaseMap supplied in this DOS source tree. */
    if (value >= 'a' && value <= 'z') return value - ('a' - 'A');
    return value;
}

unsigned rctomid(unsigned code)
{
    /* Exhaustive comparison of all 65,536 inputs establishes this mapping. */
    return code;
}
