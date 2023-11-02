import { TextContent, TextList, TextListItem, TextListItemVariants, TextListVariants } from "@patternfly/react-core";
import React from "react";

type UserInfoProps = {
  userinfo: unknown
}
export const UserInfo = (props: UserInfoProps): React.ReactElement => {
  const userinfo: any = props.userinfo;
  return (
              <TextContent>
                <TextList component={TextListVariants.dl}>
                  <TextListItem component={TextListItemVariants.dt}>Quay.io User name</TextListItem>
                  <TextListItem component={TextListItemVariants.dd}>{userinfo.username}</TextListItem>

                  <TextListItem component={TextListItemVariants.dt}>Enabled</TextListItem>
                  <TextListItem component={TextListItemVariants.dd}>{userinfo.enabled.toString()}</TextListItem>

                  <TextListItem component={TextListItemVariants.dt}>Is Paid User</TextListItem>
                  <TextListItem component={TextListItemVariants.dd}>{userinfo.paid_user.toString()}</TextListItem>

                  <TextListItem component={TextListItemVariants.dt}>Last Accessed</TextListItem>
                  <TextListItem component={TextListItemVariants.dd}>{userinfo.last_accessed}</TextListItem>

                  <TextListItem component={TextListItemVariants.dt}>Is Organization</TextListItem>
                  <TextListItem component={TextListItemVariants.dd}>{userinfo.is_organization.toString()}</TextListItem>

                  <TextListItem component={TextListItemVariants.dt}>Company</TextListItem>
                  <TextListItem component={TextListItemVariants.dd}>{userinfo.company}</TextListItem>

                  <TextListItem component={TextListItemVariants.dt}>Creation date</TextListItem>
                  <TextListItem component={TextListItemVariants.dd}>{userinfo.creation_date}</TextListItem>

                  <TextListItem component={TextListItemVariants.dt}>Last Accessed on</TextListItem>
                  <TextListItem component={TextListItemVariants.dd}>{userinfo.last_accessed}</TextListItem>

                  <TextListItem component={TextListItemVariants.dt}>Invoice Email</TextListItem>
                  <TextListItem component={TextListItemVariants.dd}>{userinfo.invoice_email}</TextListItem>

                  <TextListItem component={TextListItemVariants.dt}>Stripe Id</TextListItem>
                  <TextListItem component={TextListItemVariants.dd}>{userinfo.stripe_id}</TextListItem>

                  <TextListItem component={TextListItemVariants.dt}>Private Repositories count</TextListItem>
                  <TextListItem component={TextListItemVariants.dd}>{userinfo.private_repo_count}</TextListItem>

                  <TextListItem component={TextListItemVariants.dt}>Public Repositories count</TextListItem>
                  <TextListItem component={TextListItemVariants.dd}>{userinfo.public_repo_count}</TextListItem>
                </TextList>
              </TextContent>)
}
