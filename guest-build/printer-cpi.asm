; Project86 build wrapper for the published Microsoft printer code-page data.
; The build script substitutes CPI_DATA with 4201.INC or 4208.INC.
CODE SEGMENT PUBLIC 'CODE'
ASSUME CS:CODE,DS:NOTHING,ES:NOTHING,SS:NOTHING
ORG 0
INCLUDE CPI_DATA
CODE ENDS
END
