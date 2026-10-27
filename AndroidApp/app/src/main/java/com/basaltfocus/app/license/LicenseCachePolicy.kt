package com.basaltfocus.app.license

object LicenseCachePolicy {
    /**
     * Matches Windows: offline grace is unbounded until a definitive reply arrives.
     * There is deliberately no age limit. Persistence must bind cachedLicensed to this
     * device's hash before calling this policy, so a restored backup cannot reuse a seat.
     */
    fun keepAccess(cachedLicensed: Boolean, result: LicenseResult): Boolean =
        if (result.definitive) result.isPro else cachedLicensed
}
