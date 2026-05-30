/**
 * Create Axes integration user for JWT connect flow.
 * Username: axes.integration@<15-char-org-id>.com
 */
String orgKey = UserInfo.getOrganizationId().substring(0, 15).toLowerCase();
String username = 'axes.integration@' + orgKey + '.com';

List<User> existing = [SELECT Id, Username FROM User WHERE Username = :username LIMIT 1];
if (!existing.isEmpty()) {
    System.debug('INTEGRATION_USER_EXISTS id=' + existing[0].Id + ' username=' + existing[0].Username);
} else {
    Profile platformProfile = [
        SELECT Id
        FROM Profile
        WHERE Name = 'Standard Platform User'
        LIMIT 1
    ];
    User integrationUser = new User(
        Username = username,
        LastName = 'Integration',
        FirstName = 'Axes',
        Alias = 'axesint',
        Email = 'axes.integration+' + orgKey + '@example.com',
        EmailEncodingKey = 'UTF-8',
        LanguageLocaleKey = 'en_US',
        LocaleSidKey = 'en_US',
        TimeZoneSidKey = 'America/Los_Angeles',
        ProfileId = platformProfile.Id
    );
    insert integrationUser;
    System.debug('INTEGRATION_USER_CREATED id=' + integrationUser.Id + ' username=' + integrationUser.Username);
}
