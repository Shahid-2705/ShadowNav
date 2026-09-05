# The estimator is reached only from app code, never by reflection, so R8 is
# free to inline and rename it. Nothing here needs keeping.
#
# Kept deliberately empty rather than adding blanket -keep rules: a -keep on
# the core package would defeat the shrinking this build type exists for.
-dontwarn org.jetbrains.annotations.**
