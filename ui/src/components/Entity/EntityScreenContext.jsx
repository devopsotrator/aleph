import React, { Component } from 'react';
import { connect } from 'react-redux';

import Screen from 'src/components/Screen/Screen';
import EntityContextLoader from 'src/components/Entity/EntityContextLoader';
import EntityToolbar from 'src/components/Entity/EntityToolbar';
import EntityInfoMode from 'src/components/Entity/EntityInfoMode';
import EntityViewsMenu from 'src/components/ViewsMenu/EntityViewsMenu';
import LoadingScreen from 'src/components/Screen/LoadingScreen';
import ErrorScreen from 'src/components/Screen/ErrorScreen';
import { DualPane, Breadcrumbs, Entity } from 'src/components/common';
import { selectEntity } from 'src/selectors';
import { queryEntitySimilar } from "src/queries";
import { selectEntitiesResult, selectEntityTags } from "src/selectors";
import { withRouter } from "react-router";


class EntityScreenContext extends Component {
  render() {
    const { entity, entityId, activeMode, screenTitle, similar, tags } = this.props;
    if (entity.isError) {
      return <ErrorScreen error={entity.error} />;
    }
    if (entity.shouldLoad || entity.isLoading) {
      return (
        <EntityContextLoader entityId={entityId}>
          <LoadingScreen />
        </EntityContextLoader>
      ); 
    }

    const breadcrumbs = (
      <Breadcrumbs collection={entity.collection}>
        <li>
          <Entity.Link entity={entity} className="pt-breadcrumb" icon truncate={30}/>
        </li>
        {screenTitle && (
          <li>
            <span className="pt-breadcrumb pt-breadcrumb-current">{screenTitle}</span>
          </li>
        )}
      </Breadcrumbs>
    );

    return (
      <EntityContextLoader entityId={entityId}>
        <Screen title={`${screenTitle}: ${entity.name}`}>
          {breadcrumbs}
          <DualPane>
            <DualPane.ContentPane className="view-menu-flex-direction">
              <EntityViewsMenu tags={tags} similar={similar} entity={entity} activeMode={activeMode} isPreview={false}/>
              <div className="screen-children">
                {this.props.children}
              </div>
            </DualPane.ContentPane>
            <DualPane.InfoPane className="with-heading">
              <EntityToolbar entity={entity} isPreview={false} />
              <EntityInfoMode entity={entity} isPreview={false} />
            </DualPane.InfoPane>
          </DualPane>
        </Screen>
      </EntityContextLoader>
    );
  }
}


const mapStateToProps = (state, ownProps) => {
  const { entityId, location } = ownProps;
  const entity = selectEntity(state, entityId);
  return { entity,
    similar: selectEntitiesResult(state, queryEntitySimilar(location, entity.id)),
    tags: selectEntityTags(state, entity.id)}
};

EntityScreenContext = connect(mapStateToProps, {})(EntityScreenContext);
EntityScreenContext = withRouter(EntityScreenContext);
export default (EntityScreenContext);