; Project86: session history belongs to the resident shell, not the reloadable
; transient. Sixteen 128-byte records: length byte followed by up to 127 bytes.
PUBLIC P86HCOUNT, P86HNEXT, P86HISTORY, P86HDTA, P86HDTAON
P86HCOUNT DB 0
P86HNEXT DB 0
P86HISTORY DB 2048 DUP (0)
; Cleanup survives DOS Ctrl-C's non-local return during a filesystem search.
P86HDTA DD 0
P86HDTAON DB 0
